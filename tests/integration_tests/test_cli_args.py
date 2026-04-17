"""Tests for plugin-specific CLI arguments."""

import pytest

from dsd_aws_sam.cli import validate_cli
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)
from tests.integration_tests.utils import manage_sample_project as msp


pytestmark = pytest.mark.skip_auto_dsd_call


def test_db_engine_postgres(tmp_project, request):
    """Test that --db-engine postgres uses the RDS template."""
    cmd = "python manage.py deploy --db-engine postgres"
    msp.call_deploy(tmp_project, cmd, platform="aws_sam")

    path = tmp_project / "template.yaml"
    contents = path.read_text()
    assert "RDSInstance" in contents
    assert "VPC" in contents

    settings_path = tmp_project / "blog" / "settings.py"
    settings_contents = settings_path.read_text()
    assert "dj_database_url" in settings_contents


def test_architecture_x86(tmp_project, request):
    """Test that --architecture x86_64 is reflected in the SAM template."""
    cmd = "python manage.py deploy --architecture x86_64"
    msp.call_deploy(tmp_project, cmd, platform="aws_sam")

    path = tmp_project / "template.yaml"
    contents = path.read_text()
    assert "x86_64" in contents


def test_stage_prod(tmp_project, request):
    """Test that --stage prod is reflected in config files."""
    cmd = "python manage.py deploy --stage prod"
    msp.call_deploy(tmp_project, cmd, platform="aws_sam")

    samconfig_path = tmp_project / "samconfig.toml"
    contents = samconfig_path.read_text()
    assert "prod" in contents


def test_invalid_stack_name_rejected():
    """Reject stack names containing shell metacharacters."""
    options = {"aws_stack_name": "bad-name; rm -rf /"}
    with pytest.raises(DSDCommandError, match="Invalid stack name"):
        validate_cli(options)


def test_valid_stack_name_accepted():
    """Accept stack names with only letters, numbers, and hyphens."""
    options = {"aws_stack_name": "my-project-123"}
    validate_cli(options)
