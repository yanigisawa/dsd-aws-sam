"""Unit tests for PlatformDeployer class logic.

Covers the methods with meaningful in-class branching:
- __init__ (S3 bucket name format)
- _set_stack_name (explicit vs derived, validation)
- _show_success_message (automate_all x db_engine branching)
- _add_requirements (conditional postgres packages)
"""

import re

import pytest

from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


S3_BUCKET_RE = re.compile(r"^dsd-aws-sam-[0-9a-f]{8}$")


class TestInit:
    def test_s3_bucket_has_expected_prefix_and_uuid_suffix(self, deployer):
        assert S3_BUCKET_RE.fullmatch(deployer._s3_bucket)

    def test_s3_bucket_is_unique_per_instance(self, stub_config):
        from dsd_aws_sam.platform_deployer import PlatformDeployer

        a = PlatformDeployer()
        b = PlatformDeployer()
        assert a._s3_bucket != b._s3_bucket

    def test_deployed_url_starts_empty(self, deployer):
        assert deployer.deployed_url == ""


class TestSetStackName:
    def test_uses_explicit_stack_name_verbatim(self, deployer, stub_config):
        _, pc = stub_config
        pc.aws_stack_name = "explicit-name"

        deployer._set_stack_name()

        assert deployer.stack_name == "explicit-name"

    def test_derives_from_project_name_and_stage(self, deployer, stub_config):
        dc, pc = stub_config
        dc.local_project_name = "my_project"
        pc.aws_stack_name = None
        pc.stage = "dev"

        deployer._set_stack_name()

        assert deployer.stack_name == "my-project-dev"

    def test_replaces_all_underscores_in_project_name(self, deployer, stub_config):
        dc, pc = stub_config
        dc.local_project_name = "a_b_c_project"
        pc.aws_stack_name = None
        pc.stage = "prod"

        deployer._set_stack_name()

        assert deployer.stack_name == "a-b-c-project-prod"

    def test_derived_name_includes_stage(self, deployer, stub_config):
        dc, pc = stub_config
        dc.local_project_name = "blog"
        pc.aws_stack_name = None
        pc.stage = "staging"

        deployer._set_stack_name()

        assert deployer.stack_name == "blog-staging"

    def test_rejects_invalid_explicit_stack_name(self, deployer, stub_config):
        _, pc = stub_config
        pc.aws_stack_name = "has underscores_and spaces"

        with pytest.raises(DSDCommandError):
            deployer._set_stack_name()


class TestShowSuccessMessage:
    def test_automate_all_with_postgres_uses_rds_message(
        self, deployer, stub_config, monkeypatch
    ):
        dc, pc = stub_config
        dc.automate_all = True
        pc.db_engine = "postgres"
        deployer.deployed_url = "https://example.com"

        captured = {}

        def fake_rds(url):
            captured["called"] = "rds"
            captured["url"] = url
            return "rds-msg"

        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_with_rds",
            fake_rds,
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_automate_all",
            lambda url: pytest.fail("should not call automate_all variant"),
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg",
            lambda **kw: pytest.fail("should not call configure-only variant"),
        )

        deployer._show_success_message()

        assert captured == {"called": "rds", "url": "https://example.com"}

    def test_automate_all_with_sqlite_uses_automate_all_message(
        self, deployer, stub_config, monkeypatch
    ):
        dc, pc = stub_config
        dc.automate_all = True
        pc.db_engine = "sqlite"
        deployer.deployed_url = "https://example.com"

        captured = {}

        def fake_automate(url):
            captured["called"] = "automate"
            captured["url"] = url
            return "automate-msg"

        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_automate_all",
            fake_automate,
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_with_rds",
            lambda url: pytest.fail("should not call rds variant"),
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg",
            lambda **kw: pytest.fail("should not call configure-only variant"),
        )

        deployer._show_success_message()

        assert captured == {"called": "automate", "url": "https://example.com"}

    def test_configure_only_uses_plain_success_message_with_log_output(
        self, deployer, stub_config, monkeypatch
    ):
        dc, _ = stub_config
        dc.automate_all = False
        dc.log_output = "some-log-path"

        captured = {}

        def fake_plain(log_output=""):
            captured["called"] = "plain"
            captured["log_output"] = log_output
            return "plain-msg"

        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg", fake_plain
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_automate_all",
            lambda url: pytest.fail("should not call automate_all variant"),
        )
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.platform_msgs.success_msg_with_rds",
            lambda url: pytest.fail("should not call rds variant"),
        )

        deployer._show_success_message()

        assert captured == {"called": "plain", "log_output": "some-log-path"}


class TestAddRequirements:
    def test_sqlite_requirements(self, deployer, stub_config, monkeypatch):
        _, pc = stub_config
        pc.db_engine = "sqlite"
        calls = []
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.plugin_utils.add_package",
            lambda package, version="": calls.append((package, version)),
        )

        deployer._add_requirements()

        assert calls == [
            ("mangum", "==0.21.0"),
            ("django-storages", "==1.14.4"),
            ("boto3", "==1.35.93"),
        ]

    def test_postgres_adds_db_packages(self, deployer, stub_config, monkeypatch):
        _, pc = stub_config
        pc.db_engine = "postgres"
        calls = []
        monkeypatch.setattr(
            "dsd_aws_sam.platform_deployer.plugin_utils.add_package",
            lambda package, version="": calls.append((package, version)),
        )

        deployer._add_requirements()

        assert calls == [
            ("mangum", "==0.21.0"),
            ("django-storages", "==1.14.4"),
            ("boto3", "==1.35.93"),
            ("psycopg2-binary", "==2.9.10"),
            ("dj-database-url", "==2.3.0"),
        ]
