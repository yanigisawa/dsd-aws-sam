"""Extends the core django-simple-deploy CLI for AWS Lambda."""

import re
import shlex
import subprocess

from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

from . import deploy_messages as platform_msgs
from .plugin_config import plugin_config


STACK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class PluginCLI:

    def __init__(self, parser):
        """Add plugin-specific args."""
        group_desc = "Full documentation: https://github.com/django-simple-deploy/dsd-aws-sam"
        plugin_group = parser.add_argument_group(
            title="Options for dsd-aws-sam",
            description=group_desc,
        )

        plugin_group.add_argument(
            "--aws-region",
            type=str,
            help="AWS region for deployment (default: auto-detect or us-east-1).",
            default="",
        )

        plugin_group.add_argument(
            "--aws-stack-name",
            type=str,
            help="CloudFormation stack name (default: <project>-<stage>).",
            default="",
        )

        plugin_group.add_argument(
            "--db-engine",
            type=str,
            choices=["sqlite", "postgres"],
            help="Database engine: sqlite (ephemeral/dev) or postgres (RDS).",
            default="sqlite",
        )

        plugin_group.add_argument(
            "--architecture",
            type=str,
            choices=["arm64", "x86_64"],
            help="Lambda architecture (default: arm64, cheaper on Graviton).",
            default="arm64",
        )

        plugin_group.add_argument(
            "--stage",
            type=str,
            help="Deployment stage: dev, staging, or prod.",
            default="dev",
        )


def validate_cli(options):
    """Validate options that were passed to CLI."""
    _validate_region(options.get("aws_region", ""))
    _validate_stage(options.get("stage", "dev"))
    validate_stack_name(options.get("aws_stack_name", ""))

    plugin_config.db_engine = options.get("db_engine", "sqlite")
    plugin_config.architecture = options.get("architecture", "arm64")
    plugin_config.stage = options.get("stage", "dev")
    plugin_config.aws_stack_name = options.get("aws_stack_name", "")


def validate_stack_name(stack_name):
    """Validate an explicit CloudFormation stack name, if provided."""
    if not stack_name:
        return

    if not STACK_NAME_PATTERN.fullmatch(stack_name):
        raise DSDCommandError(platform_msgs.invalid_stack_name(stack_name))


def _validate_region(region):
    """Validate and set the AWS region."""
    if not region:
        # Auto-detect from AWS CLI configuration.
        if not dsd_config.unit_testing:
            try:
                cmd = "aws configure get region"
                cmd_parts = shlex.split(cmd)
                output = subprocess.run(cmd_parts, capture_output=True, text=True)
                if output.returncode == 0 and output.stdout.strip():
                    plugin_config.aws_region = output.stdout.strip()
                    return
            except FileNotFoundError:
                pass
        # Fall back to default.
        plugin_config.aws_region = "us-east-1"
        return

    plugin_config.aws_region = region


def _validate_stage(stage):
    """Validate the deployment stage."""
    valid_stages = ["dev", "staging", "prod"]
    if stage not in valid_stages:
        msg = f"Invalid stage '{stage}'. Must be one of: {', '.join(valid_stages)}"
        raise DSDCommandError(msg)
