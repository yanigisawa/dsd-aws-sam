"""A collection of messages used in the AWS Lambda deployment plugin."""

from textwrap import dedent


confirm_automate_all = """
The --automate-all flag means the deploy command will:
- Verify your AWS CLI and SAM CLI are configured.
- Create an S3 bucket for static files.
- Configure your project for deployment on AWS Lambda.
- Commit all changes to your project that are necessary for deployment.
- Run `sam build` to package your Lambda function.
- Run `sam deploy` to create your CloudFormation stack.
- Run `collectstatic` and `migrate` via Lambda invocation.
"""

cancel_aws_sam = """
Okay, cancelling AWS Lambda configuration and deployment.
"""

aws_cli_not_installed = """
In order to deploy to AWS Lambda, you need to install the AWS CLI.
  See here: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
After installing the CLI, configure it with `aws configure` and then run
the deploy command again.
"""

aws_cli_not_configured = """
The AWS CLI is installed but not configured. Please run:
  $ aws configure
This will set up your AWS access key, secret key, and default region.
Then run the deploy command again.
"""

sam_cli_not_installed = """
In order to deploy to AWS Lambda, you need to install the AWS SAM CLI.
  See here: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
After installing the SAM CLI, run the deploy command again.
"""

docker_not_available = """
Warning: Docker does not appear to be running.

Docker is recommended for `sam build` to ensure Lambda-compatible packages.
Without Docker, `sam build` will use your local Python environment, which
may produce incompatible binaries for native dependencies.

You can install Docker from: https://docs.docker.com/get-docker/
"""

lambda_settings_found = """
There is already an AWS Lambda-specific settings block in settings.py. Is it okay to
overwrite this block, and everything that follows in settings.py?
"""

cant_overwrite_settings = """
In order to configure the project for deployment, we need to write an AWS Lambda-specific
settings block. Please remove the current AWS Lambda-specific settings, and then run
the deploy command again.
"""

sam_build_failed = """
The `sam build` command failed.

This usually means there was a problem packaging your project's dependencies.
Common causes:
- Docker is not running (needed for native dependencies)
- A dependency has no compatible wheel for the Lambda runtime

Check the output above for specific error messages.
"""

sam_deploy_failed = """
The `sam deploy` command failed.

This usually means there was a problem creating the CloudFormation stack.
Common causes:
- Insufficient IAM permissions
- A stack with the same name already exists in a failed state
- A resource limit was reached

Check the output above for specific error messages. You may also check
the CloudFormation console for detailed stack events.
"""

sqlite_warning = """
Note: You are deploying with SQLite (the default). On AWS Lambda, the filesystem
is ephemeral -- data stored in SQLite will NOT persist across Lambda cold starts.

SQLite mode is suitable for demos and initial testing only.
For a production deployment, re-run with --db-engine postgres to use RDS.
"""

# --- Dynamic strings ---


def bucket_creation_failed(bucket_name):
    """Bucket creation failed message with bucket name."""
    msg = dedent(
        f"""
        Failed to create S3 bucket "{bucket_name}" for static files.
        This usually means there is already a bucket with the same name, or the bucket name is not
        globally unique. S3 bucket names must be globally unique across all AWS users.
        Please choose a different bucket name and run the deploy command again.
    """
    )
    return msg


def stack_name_msg(stack_name):
    """Display the CloudFormation stack name being used."""
    msg = dedent(
        f"""
        Using CloudFormation stack name: {stack_name}
    """
    )
    return msg


def invalid_stack_name(stack_name):
    """Invalid stack name message."""
    msg = dedent(
        f"""
        Invalid stack name "{stack_name}".

        Stack names may only contain letters, numbers, and hyphens.
        Example: my-project-dev
    """
    )
    return msg


def success_msg(log_output=""):
    """Success message, for configuration-only run."""
    msg = dedent(
        f"""
        --- Your project is now configured for deployment on AWS Lambda ---

        To deploy your project, you will need to:
        - Commit the changes made in the configuration process.
            $ git status
            $ git add .
            $ git commit -am "Configured project for deployment."
        - Build and deploy with SAM:
            $ sam build
            $ sam deploy
        - Run migrations (if using a database):
            $ aws lambda invoke --function-name <stack>-DjangoFunction \\
                --payload '{{"manage": "migrate --noinput"}}' /dev/stdout
        - Collect static files:
            $ aws lambda invoke --function-name <stack>-DjangoFunction \\
                --payload '{{"manage": "collectstatic --noinput"}}' /dev/stdout

        As you develop your project further:
        - Make local changes
        - Commit your changes
        - Run `sam build && sam deploy` to push updates
    """
    )
    if log_output:
        msg += dedent(
            """
        - You can find a full record of this configuration in the dsd_logs directory.
        """
        )
    return msg


def success_msg_automate_all(deployed_url):
    """Success message, when using --automate-all."""
    msg = dedent(
        f"""

        --- Your project should now be deployed on AWS Lambda ---

        Your project is available at:
          {deployed_url}

        Note: It may take a minute for the API Gateway to become fully available.
        If you see a 5xx error, wait a moment and refresh.

        To push updates:
          $ sam build && sam deploy

        To run management commands:
          $ aws lambda invoke --function-name <stack>-DjangoFunction \\
              --payload '{{"manage": "migrate --noinput"}}' /dev/stdout
    """
    )
    return msg


def success_msg_with_rds(deployed_url):
    """Success message with RDS-specific notes."""
    msg = dedent(
        f"""

        --- Your project is deployed on AWS Lambda with RDS PostgreSQL ---

        Your project is available at:
          {deployed_url}

        Your RDS database has been provisioned. Note that RDS instances can take
        several minutes to become available after initial creation.

        Migrations have been run automatically. To run additional management commands:
          $ aws lambda invoke --function-name <stack>-DjangoFunction \\
              --payload '{{"manage": "<command>"}}' /dev/stdout

        To push updates:
          $ sam build && sam deploy
    """
    )
    return msg
