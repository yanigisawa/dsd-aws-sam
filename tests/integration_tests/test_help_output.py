"""Tests for CLI help output of dsd-aws-sam."""

from pathlib import Path

import pytest

from tests.integration_tests.utils import manage_sample_project as msp


pytestmark = pytest.mark.skip_auto_dsd_call


def test_plugin_help_output(tmp_project, request):
    """Test that dsd-aws-sam CLI args are included in help output."""
    cmd = "python manage.py deploy --help"
    stdout, stderr = msp.call_deploy(tmp_project, cmd)

    # Verify plugin-specific arguments are listed.
    path_reference = (
        Path(__file__).parent / "reference_files" / "plugin_help_text.txt"
    )
    help_lines = path_reference.read_text().splitlines()

    for line in help_lines:
        if line.strip():
            assert line in stdout, f"Expected help line not found: {line}"
