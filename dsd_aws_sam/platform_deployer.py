"""Manages all AWS Lambda-specific aspects of the deployment process.

Uses Mangum as the ASGI-to-Lambda adapter and AWS SAM as the deployment tooling.
"""

import json
import os
import re
import shlex
from pathlib import Path
from uuid import uuid4
from . import deploy_messages as platform_msgs
from .cli import validate_stack_name
from .plugin_config import plugin_config

from django_simple_deploy.management.commands.utils import plugin_utils
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


# Centralized runtime dependency pins for configured projects.
# Update these values intentionally when validating a new known-good set.
LAMBDA_RUNTIME_DEPENDENCY_VERSIONS = {
    "mangum": "0.21.0",
    "django-storages": "1.14.4",
    "boto3": "1.35.93",
}

POSTGRES_RUNTIME_DEPENDENCY_VERSIONS = {
    "psycopg2-binary": "2.9.10",
    "dj-database-url": "2.3.0",
}


class PlatformDeployer:
    """Perform the initial deployment to AWS Lambda.

    If --automate-all is used, carry out an actual deployment.
    If not, do all configuration work so the user only has to commit changes
    and run `sam build && sam deploy`.
    """

    def __init__(self):
        self.templates_path = Path(__file__).parent / "templates"
        self.deployed_url = ""
        # Test buckets get a distinct prefix so the integration-test teardown
        # can target them without ever touching real deployment artifacts.
        prefix = "dsd-aws-sam-test" if dsd_config.unit_testing else "dsd-aws-sam"
        self._s3_bucket = f"{prefix}-{str(uuid4())[:8]}"

    # --- Public methods ---

    def deploy(self, *args, **options):
        """Coordinate the overall configuration and deployment."""
        plugin_utils.write_output(
            "\nConfiguring project for deployment to AWS Lambda..."
        )

        self._validate_platform()
        self._set_stack_name()

        self._add_lambda_handler()
        self._add_sam_template()
        self._add_samconfig()
        self._add_static_dir()
        self._modify_settings()
        self._add_requirements()
        self._ensure_asgi()

        # self._add_aws_sam_to_gitignore()

        if not dsd_config.unit_testing:
            self.get_or_create_s3_bucket(self._s3_bucket)

        self._conclude_automate_all()
        self._show_success_message()

    # --- Helper methods for deploy() ---

    def _validate_platform(self):
        """Make sure the local environment supports deployment to AWS Lambda."""
        if dsd_config.unit_testing:
            self.deployed_project_name = dsd_config.deployed_project_name
            return

        self._check_lambda_settings()
        self._validate_aws_cli()
        self._validate_sam_cli()
        self._check_docker()

    def _set_stack_name(self):
        """Determine the CloudFormation stack name."""
        if plugin_config.aws_stack_name:
            self.stack_name = plugin_config.aws_stack_name
        else:
            project_name = dsd_config.local_project_name.replace("_", "-")
            self.stack_name = f"{project_name}-{plugin_config.stage}"

        # Defense in depth: validate again at deploy-time before shell usage.
        validate_stack_name(self.stack_name)

        plugin_utils.write_output(
            platform_msgs.stack_name_msg(self.stack_name)
        )

    def _add_lambda_handler(self):
        """Add the Mangum-based Lambda handler."""
        template_path = self.templates_path / "lambda_handler.py"
        context = {
            "django_project_name": dsd_config.local_project_name,
        }
        contents = plugin_utils.get_template_string(template_path, context)
        path = dsd_config.project_root / "lambda_handler.py"
        plugin_utils.add_file(path, contents)

    def _add_sam_template(self):
        """Add the SAM/CloudFormation template."""
        if plugin_config.db_engine == "postgres":
            template_name = "template_with_rds.yaml"
        else:
            template_name = "template.yaml"

        template_path = self.templates_path / template_name
        context = {
            "stack_name": self.stack_name,
            "architecture": plugin_config.architecture,
            "stage": plugin_config.stage,
        }
        contents = plugin_utils.get_template_string(template_path, context)
        path = dsd_config.project_root / "template.yaml"
        plugin_utils.add_file(path, contents)

    def _add_samconfig(self):
        """Add the SAM configuration file."""
        template_path = self.templates_path / "samconfig.toml"
        context = {
            "stack_name": self.stack_name,
            "aws_region": plugin_config.aws_region,
            "stage": plugin_config.stage,
            "db_engine": plugin_config.db_engine,
            "s3_bucket": self._s3_bucket,
        }
        contents = plugin_utils.get_template_string(template_path, context)
        path = dsd_config.project_root / "samconfig.toml"
        plugin_utils.add_file(path, contents)

    def _add_static_dir(self):
        """Ensure a static/ directory exists with a placeholder."""
        static_dir = dsd_config.project_root / "static"
        plugin_utils.add_dir(static_dir)

        placeholder = static_dir / ".gitkeep"
        if not placeholder.exists():
            placeholder.write_text("")
            plugin_utils.write_output(f"    Added {placeholder}")

    def _modify_settings(self):
        """Configure the active Django settings module for AWS Lambda.

        Two strategies based on the layout detected in the target file:

        - **Stock path:** the file is an unmodified `django-admin startproject`
          settings.py. Rewrite SECRET_KEY, DEBUG, ALLOWED_HOSTS and STATIC_URL
          in place to read from env vars set by the SAM template, and append
          Lambda-specific settings (STORAGES, LOGGING, CSRF_TRUSTED_ORIGINS,
          plus a Postgres DATABASE_URL override when applicable).

        - **Sidecar path:** the file has been customized (cookiecutter-django,
          django-environ, split settings). Generate an `aws_sam_settings.py`
          module next to it and append a single `from .aws_sam_settings
          import *` line. User-authored assignments are never rewritten.

        The target file is resolved from DJANGO_SETTINGS_MODULE (the canonical
        Django way to point at the active settings module), falling back to
        the module declared in manage.py and, as a last resort, to whatever
        dsd core populated into `dsd_config.settings_path`.
        """
        settings_path = self._resolve_settings_target()
        text = settings_path.read_text()

        if self._is_stock_layout(text):
            self._apply_stock_strategy(settings_path, text)
        else:
            self._apply_sidecar_strategy(settings_path)

    def _resolve_settings_target(self):
        """Return the Path of the active Django settings module.

        Resolution order:
          1. DJANGO_SETTINGS_MODULE env var (Django's canonical pointer).
          2. The `os.environ.setdefault("DJANGO_SETTINGS_MODULE", ...)` value
             declared in manage.py.
          3. `dsd_config.settings_path` (what dsd core already found).
        """
        for candidate_mod in (
            os.environ.get("DJANGO_SETTINGS_MODULE"),
            self._parse_settings_module_from_manage_py(),
        ):
            if not candidate_mod:
                continue
            rel = candidate_mod.replace(".", "/") + ".py"
            candidate = dsd_config.project_root / rel
            if candidate.exists():
                return candidate

        return dsd_config.settings_path

    def _parse_settings_module_from_manage_py(self):
        """Pull DJANGO_SETTINGS_MODULE out of the project's manage.py, if present."""
        manage_py = dsd_config.project_root / "manage.py"
        if not manage_py.exists():
            return None
        m = re.search(
            r"""os\.environ\.setdefault\(\s*["']DJANGO_SETTINGS_MODULE["']\s*,\s*["']([^"']+)["']""",
            manage_py.read_text(),
        )
        return m.group(1) if m else None

    def _is_stock_layout(self, text):
        """Return True when the settings file matches stock django-admin output.

        The three canonical markers (SECRET_KEY with a django-insecure value,
        `DEBUG = True`, and `ALLOWED_HOSTS = []`) all being present is a
        strong signal that the surgical-regex strategy will succeed.
        """
        markers = (
            r'^SECRET_KEY = "django-insecure-[^"\n]+"$',
            r"^DEBUG = True$",
            r"^ALLOWED_HOSTS = \[\]$",
        )
        return all(re.search(p, text, re.MULTILINE) for p in markers)

    def _apply_stock_strategy(self, settings_path, text):
        """Surgical-regex rewrites plus an appended Lambda settings block."""
        text = self._ensure_import_os(text)
        text = self._rewrite_existing_settings_lines(text)
        text += self._build_lambda_settings_block()
        plugin_utils.modify_file(settings_path, text)

    def _apply_sidecar_strategy(self, settings_path):
        """Write aws_sam_settings.py alongside the target and import it.

        Leaves user-authored lines in the target file untouched; the sidecar
        module's env-var-gated assignments activate only when the SAM runtime
        has populated the relevant env vars.
        """
        template_path = self.templates_path / "aws_sam_settings.py"
        context = {
            "aws_region": plugin_config.aws_region,
            "db_engine": plugin_config.db_engine,
        }
        contents = plugin_utils.get_template_string(template_path, context)
        sidecar_path = settings_path.parent / "aws_sam_settings.py"
        plugin_utils.add_file(sidecar_path, contents)

        import_line = "from .aws_sam_settings import *"
        text = settings_path.read_text()
        if import_line in text:
            plugin_utils.write_output(
                f"  Sidecar import already present in {settings_path.as_posix()}; skipping."
            )
            return

        if not text.endswith("\n"):
            text += "\n"
        text += f"\n# AWS SAM settings.\n{import_line}\n"
        plugin_utils.modify_file(settings_path, text)

    def _ensure_import_os(self, text):
        """Add `import os` to settings.py if missing."""
        if re.search(r"^import os$", text, re.MULTILINE):
            return text
        return re.sub(
            r"^from pathlib import Path$",
            "import os\nfrom pathlib import Path",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    def _rewrite_existing_settings_lines(self, text):
        """Replace stock Django-generated settings lines with env-driven forms.

        Each replacement is idempotent: on re-run, the original pattern no
        longer matches, so the line is left as-is.
        """
        # SECRET_KEY -- read from env, fall back to the existing key.
        text = re.sub(
            r'^SECRET_KEY = ("django-insecure-[^"\n]+")$',
            r'SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", \1)',
            text,
            count=1,
            flags=re.MULTILINE,
        )

        # DEBUG -- read from env, default True to preserve local dev behavior.
        text = re.sub(
            r"^DEBUG = True$",
            'DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1")',
            text,
            count=1,
            flags=re.MULTILINE,
        )

        # ALLOWED_HOSTS -- split a comma-separated env var; empty locally.
        text = re.sub(
            r"^ALLOWED_HOSTS = \[\]$",
            'ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",") if os.environ.get("ALLOWED_HOSTS") else []',
            text,
            count=1,
            flags=re.MULTILINE,
        )

        # STATIC_URL -- serve from S3 when the bucket env var is set.
        text = re.sub(
            r'^STATIC_URL = "static/"$',
            'STATIC_URL = f"https://{os.environ[\'STATIC_FILES_BUCKET\']}.s3.amazonaws.com/static/" if os.environ.get("STATIC_FILES_BUCKET") else "static/"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        return text

    def _build_lambda_settings_block(self):
        """Build the Lambda-specific settings appended to the end of settings.py.

        Each value is env-var-driven so local dev keeps working unchanged when
        the relevant env vars are absent.
        """
        aws_region = plugin_config.aws_region
        lines = [
            "",
            "# AWS SAM settings.",
            "CSRF_TRUSTED_ORIGINS = (",
            '    os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")',
            '    if os.environ.get("CSRF_TRUSTED_ORIGINS")',
            "    else []",
            ")",
            "",
            'AWS_STORAGE_BUCKET_NAME = os.environ.get("STATIC_FILES_BUCKET", "")',
            f'AWS_S3_REGION_NAME = os.environ.get("AWS_REGION", "{aws_region}")',
            "AWS_DEFAULT_ACL = None",
            "STORAGES = (",
            '    {"staticfiles": {"BACKEND": "storages.backends.s3boto3.S3StaticStorage"}}',
            "    if AWS_STORAGE_BUCKET_NAME",
            '    else {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}',
            ")",
            "",
            "# CloudWatch-compatible logging.",
            "LOGGING = {",
            '    "version": 1,',
            '    "disable_existing_loggers": False,',
            '    "formatters": {',
            '        "standard": {',
            '            "format": "[%(levelname)s] %(name)s: %(message)s",',
            "        },",
            "    },",
            '    "handlers": {',
            '        "console": {',
            '            "class": "logging.StreamHandler",',
            '            "formatter": "standard",',
            "        },",
            "    },",
            '    "root": {',
            '        "handlers": ["console"],',
            '        "level": "INFO",',
            "    },",
            "}",
        ]

        if plugin_config.db_engine == "postgres":
            # dj_database_url is pinned in POSTGRES_RUNTIME_DEPENDENCY_VERSIONS,
            # so the import is safe at module load time for postgres deploys.
            lines += [
                "",
                "import dj_database_url",
                "",
                '_database_url = os.environ.get("DATABASE_URL")',
                'DATABASES["default"] = (',
                "    dj_database_url.parse(_database_url) if _database_url else DATABASES[\"default\"]",
                ")",
            ]

        return "\n".join(lines) + "\n"

    def _add_requirements(self):
        """Add requirements for deploying to AWS Lambda."""
        requirements = dict(LAMBDA_RUNTIME_DEPENDENCY_VERSIONS)
        if plugin_config.db_engine == "postgres":
            requirements.update(POSTGRES_RUNTIME_DEPENDENCY_VERSIONS)

        for package_name, version in requirements.items():
            plugin_utils.add_package(package_name, version=f"=={version}")

    def _ensure_asgi(self):
        """Ensure the project has an ASGI application module.

        Django projects created with startproject include asgi.py by default,
        but we verify it exists since Mangum requires it.
        """
        # The asgi.py is typically at <project_name>/asgi.py.
        # If settings_path is <root>/<project>/settings.py, asgi.py is in the
        # same directory.
        if dsd_config.nanodjango_project:
            return

        project_dir = dsd_config.settings_path.parent
        asgi_path = project_dir / "asgi.py"
        if not asgi_path.exists():
            plugin_utils.write_output(
                "\n  Warning: asgi.py not found. Mangum requires an ASGI application."
            )
            plugin_utils.write_output(
                f"  Expected at: {asgi_path}"
            )
            plugin_utils.write_output(
                "  Django's `startproject` creates this by default."
            )
        else:
            plugin_utils.write_output(f"\n  Found asgi.py at {asgi_path}")

    def _conclude_automate_all(self):
        """Finish automating the deployment to AWS Lambda."""
        if not dsd_config.automate_all:
            if plugin_config.db_engine == "sqlite":
                plugin_utils.write_output(platform_msgs.sqlite_warning)
            return

        plugin_utils.commit_changes()

        # sam build
        plugin_utils.write_output("\n  Building Lambda package with SAM...")
        cmd = "sam build"
        try:
            plugin_utils.run_slow_command(cmd)
        except Exception:
            raise DSDCommandError(platform_msgs.sam_build_failed)

        # sam deploy
        plugin_utils.write_output("\n  Deploying to AWS with SAM...")
        cmd = "sam deploy --no-confirm-changeset --no-fail-on-empty-changeset"
        try:
            plugin_utils.run_slow_command(cmd)
        except Exception:
            raise DSDCommandError(platform_msgs.sam_deploy_failed)

        # Get the deployed URL from stack outputs.
        self._get_deployed_url()

        # Run post-deployment commands.
        self._run_post_deploy_commands()

    def _get_deployed_url(self):
        """Get the deployed URL from CloudFormation stack outputs."""
        quoted_stack_name = shlex.quote(self.stack_name)
        cmd = (
            f"aws cloudformation describe-stacks"
            f" --stack-name {quoted_stack_name}"
            f" --query \"Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue\""
            f" --output text"
        )
        output = plugin_utils.run_quick_command(cmd)
        url = output.stdout.decode().strip()
        if url:
            self.deployed_url = url
            plugin_utils.write_output(f"\n  Deployed URL: {self.deployed_url}")
        else:
            self.deployed_url = "(URL not available -- check CloudFormation console)"

    def _run_post_deploy_commands(self):
        """Run collectstatic and migrate via Lambda invocation."""
        function_name = f"{self.stack_name}-DjangoFunction"
        quoted_function_name = shlex.quote(function_name)

        # collectstatic
        plugin_utils.write_output("\n  Running collectstatic...")
        cmd = (
            f'aws lambda invoke'
            f' --function-name {quoted_function_name}'
            f' --payload \'{{"manage": "collectstatic --noinput"}}\''
            f' /dev/stdout'
        )
        output = plugin_utils.run_quick_command(cmd)
        plugin_utils.write_output(output)

        # migrate
        plugin_utils.write_output("\n  Running migrate...")
        cmd = (
            f'aws lambda invoke'
            f' --function-name {quoted_function_name}'
            f' --payload \'{{"manage": "migrate --noinput"}}\''
            f' /dev/stdout'
        )
        output = plugin_utils.run_quick_command(cmd)
        plugin_utils.write_output(output)

    def _show_success_message(self):
        """After a successful run, show a message about what to do next."""
        if dsd_config.automate_all:
            if plugin_config.db_engine == "postgres":
                msg = platform_msgs.success_msg_with_rds(self.deployed_url)
            else:
                msg = platform_msgs.success_msg_automate_all(self.deployed_url)
        else:
            msg = platform_msgs.success_msg(log_output=dsd_config.log_output)
        plugin_utils.write_output(msg)

    # --- Helper methods for _validate_platform() ---

    def _check_lambda_settings(self):
        """Check to see if an AWS SAM settings block already exists."""
        start_line = "# AWS SAM settings."
        plugin_utils.check_settings(
            "AWS SAM",
            start_line,
            platform_msgs.sam_settings_found,
            platform_msgs.cant_overwrite_settings,
        )

    def _validate_aws_cli(self):
        """Make sure the AWS CLI is installed and configured."""
        # Check AWS CLI is installed.
        cmd = "aws --version"
        try:
            output = plugin_utils.run_quick_command(cmd)
        except FileNotFoundError:
            raise DSDCommandError(platform_msgs.aws_cli_not_installed)

        if output.returncode:
            raise DSDCommandError(platform_msgs.aws_cli_not_installed)

        plugin_utils.log_info(output)

        # Check AWS CLI is configured (has credentials).
        cmd = "aws sts get-caller-identity"
        output = plugin_utils.run_quick_command(cmd)
        if output.returncode:
            raise DSDCommandError(platform_msgs.aws_cli_not_configured)

        identity = json.loads(output.stdout.decode())
        account_id = identity.get("Account", "unknown")
        msg = f"  Authenticated to AWS account: {account_id}"
        plugin_utils.write_output(msg)

    def _validate_sam_cli(self):
        """Make sure the SAM CLI is installed."""
        cmd = "sam --version"
        try:
            output = plugin_utils.run_quick_command(cmd)
        except FileNotFoundError:
            raise DSDCommandError(platform_msgs.sam_cli_not_installed)

        if output.returncode:
            raise DSDCommandError(platform_msgs.sam_cli_not_installed)

        plugin_utils.log_info(output)
        msg = f"  SAM CLI: {output.stdout.decode().strip()}"
        plugin_utils.write_output(msg)

    def _check_docker(self):
        """Check if Docker is available (recommended but not required)."""
        cmd = "docker info"
        try:
            output = plugin_utils.run_quick_command(cmd)
            if output.returncode:
                plugin_utils.write_output(platform_msgs.docker_not_available)
            else:
                plugin_utils.write_output("  Docker is available.")
        except FileNotFoundError:
            plugin_utils.write_output(platform_msgs.docker_not_available)

    def create_bucket(self, bucket_name):
        """Create an S3 bucket."""
        cmd = f"aws s3 mb s3://{bucket_name}"
        output = plugin_utils.run_quick_command(cmd)
        if output.returncode:
            raise DSDCommandError(
                platform_msgs.bucket_creation_failed(bucket_name)
            )
        plugin_utils.log_info(output)
        plugin_utils.write_output(f"  Created S3 bucket: {bucket_name}")

    def bucket_exists(self, bucket_name):
        """Check if an S3 bucket exists."""
        cmd = f"aws s3 ls s3://{bucket_name}"
        output = plugin_utils.run_quick_command(cmd)
        return output.returncode == 0

    def get_or_create_s3_bucket(self, explicit_bucket=None):
        if explicit_bucket:
            bucket = explicit_bucket  # Use user-provided
        else:
            bucket = self._s3_bucket

        # Check if bucket exists
        if not self.bucket_exists(bucket):
            self.create_bucket(bucket)  # Create if needed

        return bucket
