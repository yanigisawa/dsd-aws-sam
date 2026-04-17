"""Config class for plugin information shared with core."""

from . import deploy_messages as platform_msgs


class PluginConfig:
    """Class for managing attributes that need to be shared with core.

    Get plugin-specific attributes required by core.

    Required:
    - automate_all_supported
    - platform_name
    Optional:
    - confirm_automate_all_msg (required if automate_all_supported is True)
    """

    def __init__(self):
        self.automate_all_supported = True
        self.confirm_automate_all_msg = platform_msgs.confirm_automate_all
        self.platform_name = "AWS SAM"

        # Values from plugin CLI args.
        self.aws_region = None
        self.aws_stack_name = None
        self.db_engine = "sqlite"
        self.architecture = "arm64"
        self.stage = "dev"


# Create plugin_config once right here.
plugin_config = PluginConfig()
