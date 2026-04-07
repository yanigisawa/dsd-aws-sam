"""AWS Lambda handler for Django via Mangum.

This handler serves two purposes:
1. Routes HTTP requests from API Gateway to Django via the Mangum ASGI adapter.
2. Dispatches Django management commands when invoked with a {"manage": "..."} payload.

Usage:
  HTTP requests: Handled automatically by API Gateway -> Lambda -> Mangum -> Django.
  Management commands:
    aws lambda invoke --function-name <function-name> \
      --payload '{"manage": "migrate --noinput"}' /dev/stdout
"""

import json
import os
import subprocess
import sys

from mangum import Mangum

# Set the Django settings module.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{{ django_project_name }}.settings")

# Import Django's ASGI application.
from {{ django_project_name }}.asgi import application

# Create the Mangum handler for ASGI.
# api_gateway_base_path: strip the stage prefix from the URL path.
mangum_handler = Mangum(application, lifespan="off")


def handler(event, context):
    """Lambda entry point.

    If the event contains a "manage" key, run the specified management command.
    Otherwise, pass the event to Mangum for HTTP request handling.
    """
    if "manage" in event:
        return _run_management_command(event["manage"])

    return mangum_handler(event, context)


def _run_management_command(command_string):
    """Run a Django management command and return the output."""
    import django

    django.setup()

    from django.core.management import call_command
    from io import StringIO

    args = command_string.split()
    stdout = StringIO()
    stderr = StringIO()

    try:
        call_command(*args, stdout=stdout, stderr=stderr)
        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "command": command_string,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                }
            ),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "command": command_string,
                    "error": str(e),
                    "stderr": stderr.getvalue(),
                }
            ),
        }
