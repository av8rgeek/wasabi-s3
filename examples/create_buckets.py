#!/usr/bin/env python3
"""
Example: Create multiple buckets with a naming convention.

Demonstrates batch bucket creation across environments (prod/test)
and usage categories, collecting ARNs for policy creation.
"""

import json
import logging
from os import getenv
from wasabi_s3 import Bucket, DateTimeEncoder


def main():
    bucket_prefix = "myorg-us-east1"
    environments = [
        "prod",
        "test",
    ]
    bucket_usage = {
        "uploads": 1,
        "backups": 1,
        "assets": 1,
    }
    arn_list = []
    for env in environments:
        for bucket, count in bucket_usage.items():
            for idx in range(1, count + 1):
                bucket_name = f"{bucket_prefix}-{env}-{bucket}-{idx:02d}"
                wasabi_bucket = Bucket(bucket_name=bucket_name, region="us-east-1")
                if wasabi_bucket.create_bucket():
                    arn_list.append(wasabi_bucket.arn)
                    arn_list.append(f"{wasabi_bucket.arn}/*")
                else:
                    print(f"Failed to create bucket {bucket_name}")
    print(json.dumps(arn_list, indent=4, separators=(",", ": "), cls=DateTimeEncoder))


if __name__ == "__main__":
    main()
