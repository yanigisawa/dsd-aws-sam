"""Unit tests for validate_stack_name in dsd_aws_sam.cli.

Pure regex validation: ^[A-Za-z0-9-]+$. Empty string is a no-op (caller
supplies no explicit stack name).
"""

import pytest

from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)

from dsd_aws_sam.cli import validate_stack_name


@pytest.mark.parametrize(
    "name",
    [
        "my-app-dev",
        "Test123",
        "a",
        "a-b-c",
        "UPPER",
        "123",
        "a1-B2-c3",
    ],
)
def test_accepts_valid_names(name):
    validate_stack_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "my_app",
        "my app",
        "my.app",
        "my@app",
        "my/app",
        "my:app",
        "trailing-newline\n",
        "tab\there",
    ],
)
def test_rejects_invalid_names(name):
    with pytest.raises(DSDCommandError):
        validate_stack_name(name)


def test_empty_string_is_noop():
    validate_stack_name("")


def test_none_is_noop():
    validate_stack_name(None)
