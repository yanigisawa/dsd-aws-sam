"""Test the full, live deployment process to AWS Lambda."""

import pytest

from tests.e2e_tests.utils import it_helper_functions as it_utils
from tests.e2e_tests.utils import manage_sample_project as msp
from tests.e2e_tests import utils as platform_utils


@pytest.fixture(scope="session")
def python_cmd(tmp_project):
    """Get path to python command in test venv."""
    return it_utils.get_python_exe(tmp_project)


def test_deployment(tmp_project, cli_options, request):
    """Test the full, live deployment process to AWS Lambda."""
    python_cmd = it_utils.get_python_exe(tmp_project)

    # Run simple_deploy.
    plugin_args = ""
    if hasattr(cli_options, "plugin_args_string") and cli_options.plugin_args_string:
        plugin_args = cli_options.plugin_args_string

    it_utils.run_simple_deploy(
        python_cmd,
        "aws_sam",
        automate_all=cli_options.automate_all,
        plugin_args_string=plugin_args,
    )

    if cli_options.automate_all:
        # Get project URL from stack outputs.
        project_url, stack_name = platform_utils.get_project_url_name()
        request.config.cache.set("stack_name", stack_name)
    else:
        # Commit changes and deploy manually.
        it_utils.commit_configuration_changes()
        project_url = platform_utils.deploy_project()

    # Test the deployed app.
    remote_functionality_passed = it_utils.check_deployed_app_functionality(
        project_url
    )

    # Check local functionality still works.
    local_functionality_passed = it_utils.check_local_app_functionality(
        python_cmd, project_url
    )

    # Summarize results.
    it_utils.summarize_results(
        remote_functionality_passed, local_functionality_passed
    )

    assert remote_functionality_passed
    assert local_functionality_passed
