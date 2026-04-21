"""Fixtures for dsd-aws-sam unit tests.

Unit tests here run in isolation: no tmp Django project, no subprocess,
no filesystem writes. Fixtures stub the shared dsd_config and plugin_config
singletons with neutral defaults and silence plugin_utils.write_output so
tests can assert on class logic without noise.
"""

import pytest

from dsd_aws_sam.platform_deployer import PlatformDeployer
from dsd_aws_sam.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config


@pytest.fixture
def stub_config(monkeypatch):
    """Reset dsd_config and plugin_config to known defaults for each test.

    Returns a (dsd_config, plugin_config) tuple so tests can override specific
    attributes inline.
    """
    monkeypatch.setattr(dsd_config, "unit_testing", True, raising=False)
    monkeypatch.setattr(dsd_config, "automate_all", False, raising=False)
    monkeypatch.setattr(dsd_config, "local_project_name", "my_project", raising=False)
    monkeypatch.setattr(dsd_config, "log_output", "", raising=False)

    monkeypatch.setattr(plugin_config, "aws_stack_name", None, raising=False)
    monkeypatch.setattr(plugin_config, "stage", "dev", raising=False)
    monkeypatch.setattr(plugin_config, "db_engine", "sqlite", raising=False)

    monkeypatch.setattr(
        "dsd_aws_sam.platform_deployer.plugin_utils.write_output",
        lambda *a, **kw: None,
    )
    return dsd_config, plugin_config


@pytest.fixture
def deployer(stub_config):
    """PlatformDeployer instance with config stubbed to safe defaults."""
    return PlatformDeployer()
