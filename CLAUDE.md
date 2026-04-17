# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **dsd-aws-sam**, a plugin for [django-simple-deploy](https://github.com/django-simple-deploy/django-simple-deploy) that adds AWS Lambda deployment support. It configures Django projects to deploy as serverless applications using AWS SAM (Serverless Application Model) with Mangum as the ASGI-to-Lambda adapter.

## Build & Test Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run integration tests (excludes e2e by default via conftest.py collect_ignore)
pytest tests/integration_tests/

# Run a single test
pytest tests/integration_tests/test_aws_sam_config.py::test_creates_sam_template

# Run e2e tests (requires AWS credentials, SAM CLI, and Docker)
pytest tests/e2e_tests/

# Format code
black .

# Build package
python -m build
```

## Architecture

### Plugin System

This is a **pluggy-based plugin** for django-simple-deploy. The hook contract is defined by `django_simple_deploy` core:

- `dsd_aws_sam/__init__.py` — Exports the two required hook implementations: `dsd_get_plugin_config` and `dsd_deploy`
- `dsd_aws_sam/deploy.py` — Registers four `@django_simple_deploy.hookimpl` hooks: `dsd_get_plugin_config`, `dsd_get_plugin_cli`, `dsd_validate_cli`, and `dsd_deploy`
- `dsd_aws_sam/plugin_config.py` — `PluginConfig` singleton shared with core (exposes `platform_name`, `automate_all_supported`, and plugin-specific CLI values like `aws_region`, `db_engine`, `architecture`, `stage`)

### Deployment Flow

`PlatformDeployer` in `platform_deployer.py` orchestrates deployment:
1. Validates platform prerequisites (AWS CLI, SAM CLI, Docker)
2. Generates files from templates: `lambda_handler.py`, `template.yaml` (SAM), `samconfig.toml`, GitHub Actions workflow
3. Modifies Django settings for Lambda (S3 static files, etc.)
4. Adds required packages (`mangum`, `django-storages`, `boto3`; plus `psycopg2-binary`/`dj-database-url` for postgres)
5. If `--automate-all`: commits, runs `sam build && sam deploy`, invokes Lambda for `collectstatic`/`migrate`

Two deployment paths exist based on `--db-engine`: `sqlite` (default, ephemeral) and `postgres` (provisions RDS via `template_with_rds.yaml`).

### Templates

`dsd_aws_sam/templates/` contains Jinja-style templates processed by `plugin_utils.get_template_string()` from core. These generate the actual deployment files in the user's project.

### Test Structure

- **Integration tests** (`tests/integration_tests/`) — Use django-simple-deploy's test utilities (`tests.integration_tests.utils`) to create a temporary Django project, run `manage.py deploy`, and verify generated files. These run without AWS credentials.
- **E2e tests** (`tests/e2e_tests/`) — Perform actual AWS deployments. Excluded from default test collection via `conftest.py`. Require AWS credentials, SAM CLI, and Docker.

Tests with `pytestmark = pytest.mark.skip_auto_dsd_call` manage the deploy call themselves (e.g., to pass custom CLI args).
