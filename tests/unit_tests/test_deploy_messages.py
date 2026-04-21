"""Unit tests for pure string-builder functions in deploy_messages.py."""

from dsd_aws_sam import deploy_messages as platform_msgs


class TestBucketCreationFailed:
    def test_includes_bucket_name(self):
        msg = platform_msgs.bucket_creation_failed("my-bucket-123")
        assert "my-bucket-123" in msg

    def test_mentions_global_uniqueness_requirement(self):
        msg = platform_msgs.bucket_creation_failed("anything")
        assert "globally unique" in msg


class TestStackNameMsg:
    def test_includes_stack_name(self):
        msg = platform_msgs.stack_name_msg("blog-dev")
        assert "blog-dev" in msg

    def test_mentions_cloudformation(self):
        msg = platform_msgs.stack_name_msg("x")
        assert "CloudFormation" in msg


class TestInvalidStackName:
    def test_includes_rejected_name(self):
        msg = platform_msgs.invalid_stack_name("bad_name")
        assert "bad_name" in msg

    def test_states_allowed_characters(self):
        msg = platform_msgs.invalid_stack_name("bad_name")
        assert "letters, numbers, and hyphens" in msg


class TestSuccessMsg:
    def test_omits_log_notice_when_no_log_output(self):
        msg = platform_msgs.success_msg(log_output="")
        assert "dsd_logs" not in msg

    def test_includes_log_notice_when_log_output_set(self):
        msg = platform_msgs.success_msg(log_output="some-path")
        assert "dsd_logs" in msg

    def test_mentions_sam_build_and_deploy(self):
        msg = platform_msgs.success_msg()
        assert "sam build" in msg
        assert "sam deploy" in msg


class TestSuccessMsgAutomateAll:
    def test_includes_deployed_url(self):
        msg = platform_msgs.success_msg_automate_all("https://example.com/abc")
        assert "https://example.com/abc" in msg

    def test_mentions_api_gateway_delay(self):
        msg = platform_msgs.success_msg_automate_all("url")
        assert "API Gateway" in msg


class TestSuccessMsgWithRds:
    def test_includes_deployed_url(self):
        msg = platform_msgs.success_msg_with_rds("https://example.com/rds")
        assert "https://example.com/rds" in msg

    def test_mentions_rds_postgres(self):
        msg = platform_msgs.success_msg_with_rds("url")
        assert "RDS" in msg
        assert "PostgreSQL" in msg
