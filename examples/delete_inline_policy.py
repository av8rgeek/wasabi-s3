#!/usr/bin/env python3
"""
Example: Delete an inline policy from a group.

Demonstrates removing an inline policy from a Wasabi IAM group
and inspecting the group's properties afterward.
"""

import json
import logging
from wasabi_s3 import Group, DateTimeEncoder

LOG_LEVEL = logging.DEBUG
GROUP_NAME = "my-test-group"
POLICY_NAME = "my-inline-policy"


def main() -> None:
    logger.debug("Creating the group object")
    this_group = Group(group_name=GROUP_NAME)
    logger.debug("Deleting the inline group policy")
    this_group.delete_inline_group_policy(inline_policy_name=POLICY_NAME)
    logger.debug("Exporting the group properties")
    logger.debug(json.dumps(this_group.to_dict(), indent=4, cls=DateTimeEncoder))


def initialize_logging() -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(level=LOG_LEVEL)
    console_logging_handler = logging.StreamHandler()
    console_logging_handler.setLevel(level=LOG_LEVEL)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_logging_handler.setFormatter(formatter)
    logger.addHandler(console_logging_handler)

    wasabi_logger = logging.getLogger("wasabi_s3")
    wasabi_logger.setLevel(level=LOG_LEVEL)
    wasabi_logger.addHandler(console_logging_handler)
    return logger


if __name__ == "__main__":
    logger = initialize_logging()
    main()
