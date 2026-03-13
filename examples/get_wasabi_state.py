#!/usr/bin/env python3
"""
Example: Export a full snapshot of all Wasabi resources.

Demonstrates iterating over all users, groups, policies, and buckets
to produce a complete state export in JSON and YAML formats.
"""

from os import getenv
import json
import logging
import yaml
from wasabi_s3 import Client, User, Group, Policy, Bucket, DateTimeEncoder


def main() -> None:
    logger.debug("Starting main()")
    users: dict = {}
    groups: dict = {}
    policies: dict = {}
    buckets: dict = {}

    # Get authenticated with Wasabi
    client = Client()
    logger.debug("Client instantiated successfully")

    logger.debug("Getting billing data")
    billing_data: dict = client.get_billing_data()
    if billing_data:
        logger.debug("Got billing data")

    # Get the lists of users, groups, managed policies, and buckets
    logger.debug("Getting users")
    userlist: list[dict] = client.get_users()
    logger.debug("Getting groups")
    grouplist: list[dict] = client.get_groups()
    logger.debug("Getting managed policies")
    policylist: list[dict] = client.get_managed_policies()
    logger.debug("Getting buckets")
    bucketlist: dict[str, str] = client.get_buckets()

    # Iterate through the users, groups, managed policies, and buckets
    logger.debug("Iterating through users")
    for user in userlist:
        w_user = User(user["UserName"])
        users[w_user.username] = w_user.to_dict()
        users[w_user.username].pop("name")
    logger.debug("Iterating through groups")
    for group in grouplist:
        w_group = Group(group["GroupName"])
        groups[w_group.group_name] = w_group.to_dict()
        groups[w_group.group_name].pop("name")
    logger.debug("Iterating through managed policies")
    for policy in policylist:
        w_policy = Policy(policy["PolicyName"])
        policies[w_policy.policy_name] = w_policy.to_dict()
        policies[w_policy.policy_name].pop("name")
    logger.debug("Iterating through buckets")
    for bucket, region in bucketlist.items():
        w_bucket = Bucket(bucket, region=region, billing_data=billing_data)
        buckets[w_bucket.bucket_name] = w_bucket.to_dict()
        buckets[w_bucket.bucket_name].pop("name")

    # Combine everything into a single state object
    logger.debug("Combining everything into a single state object")
    state: dict[str, dict] = {
        "users": users,
        "groups": groups,
        "policies": policies,
        "buckets": buckets,
    }

    # Write the state object to files
    logger.debug("Writing the state object to files")
    with open("wasabi_state.json", "w") as f:
        f.write(json.dumps(state, indent=4, cls=DateTimeEncoder))

    with open("wasabi_state.yaml", "w") as f:
        f.write(yaml.dump(state, default_flow_style=False))

    print("State exported to wasabi_state.json and wasabi_state.yaml")


def initialize_logging() -> logging.Logger:
    LOG_LEVEL = logging.DEBUG
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
