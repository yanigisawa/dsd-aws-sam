"""AWS Lambda-specific test utility functions for e2e tests."""

import json
import re
import subprocess


def make_sp_call(cmd, capture_output=False):
    """Make a subprocess call."""
    cmd_parts = cmd.split()
    return subprocess.run(
        cmd_parts,
        capture_output=capture_output,
        text=True,
    )


def get_project_url_name():
    """Get the deployed project URL and stack name from CloudFormation outputs.

    Returns:
        tuple: (project_url, stack_name)
    """
    # Find the stack name from samconfig.toml.
    import toml

    samconfig = toml.load("samconfig.toml")
    stack_name = samconfig["default"]["deploy"]["parameters"]["stack_name"]

    # Get the API URL from stack outputs.
    cmd = (
        f"aws cloudformation describe-stacks"
        f" --stack-name {stack_name}"
        f" --query Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue"
        f" --output text"
    )
    output = make_sp_call(cmd, capture_output=True)
    project_url = output.stdout.strip()

    return project_url, stack_name


def deploy_project():
    """Deploy the project using SAM.

    Returns:
        str: The deployed project URL.
    """
    # Build.
    make_sp_call("sam build")

    # Deploy.
    make_sp_call("sam deploy --no-confirm-changeset --no-fail-on-empty-changeset")

    # Get the URL.
    project_url, _ = get_project_url_name()

    # Run post-deploy commands.
    import toml

    samconfig = toml.load("samconfig.toml")
    stack_name = samconfig["default"]["deploy"]["parameters"]["stack_name"]
    function_name = f"{stack_name}-DjangoFunction"

    cmd = (
        f"aws lambda invoke"
        f" --function-name {function_name}"
        f" --payload '{{\"manage\": \"migrate --noinput\"}}'"
        f" /dev/stdout"
    )
    make_sp_call(cmd, capture_output=True)

    cmd = (
        f"aws lambda invoke"
        f" --function-name {function_name}"
        f" --payload '{{\"manage\": \"collectstatic --noinput\"}}'"
        f" /dev/stdout"
    )
    make_sp_call(cmd, capture_output=True)

    return project_url


def destroy_project(stack_name=None):
    """Destroy the deployed project.

    Args:
        stack_name: CloudFormation stack name. If not provided, reads from samconfig.
    """
    if not stack_name:
        import toml

        samconfig = toml.load("samconfig.toml")
        stack_name = samconfig["default"]["deploy"]["parameters"]["stack_name"]

    cmd = f"aws cloudformation delete-stack --stack-name {stack_name}"
    make_sp_call(cmd)

    # Wait for deletion to complete.
    cmd = f"aws cloudformation wait stack-delete-complete --stack-name {stack_name}"
    make_sp_call(cmd)


def check_log(tmp_proj_dir):
    """Check that sensitive information is not logged."""
    from pathlib import Path

    path = tmp_proj_dir / "dsd_logs"
    if not path.exists():
        return False

    log_files = list(path.glob("dsd_*.log"))
    if not log_files:
        return False

    log_str = log_files[0].read_text()

    # Ensure secret key values are not logged.
    if "SECRET_KEY =" in log_str and "*value hidden*" not in log_str:
        return False

    return True
