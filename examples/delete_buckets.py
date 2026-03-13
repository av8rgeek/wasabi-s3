#!/usr/bin/env python3
"""
Example: Delete a list of buckets with dry-run support and size reporting.

Demonstrates safe bucket deletion with billing data lookup,
size/object reporting, and a dry-run mode for validation.
"""

import logging
from wasabi_s3 import Client, Bucket

DRY_RUN: bool = True
LOGLEVEL: int = logging.INFO

buckets_to_delete = [
    "myorg-us-east1-test-uploads-01",
    "myorg-us-east1-test-backups-01",
    "myorg-us-east1-test-assets-01",
]


def delete_buckets(bucket_list: list):
    """Delete all buckets in the provided list."""
    if not bucket_list:
        raise ValueError("No buckets provided to delete.")
    size: float = 0
    object_count: int = 0
    deleted_buckets: int = 0
    client = Client()
    billing_data: dict = client.get_billing_data()
    if DRY_RUN:
        logging.info("DRY RUN enabled - no buckets will be deleted")
    logging.info("Got billing data")
    for bucket in bucket_list:
        wasabi_bucket = Bucket(bucket_name=bucket, billing_data=billing_data)
        bucket_size = wasabi_bucket.get_size_gb()
        objects = wasabi_bucket.get_object_count()
        size += bucket_size
        size_tb = size / 1000
        size_str = f"{size_tb:,.2f} TB" if size_tb >= 1 else f"{size:,.2f} GB"
        bucket_size_tb = bucket_size / 1000
        bucket_size_str = f"{bucket_size_tb:,.2f} TB" if bucket_size_tb >= 1 else f"{bucket_size:,.2f} GB"
        object_count += objects
        logging.info(f"Deleting bucket {bucket}, size: {bucket_size_str}, objects: {objects:,}")
        if DRY_RUN:
            deleted_buckets += 1
        else:
            if wasabi_bucket.force_delete_bucket():
                deleted_buckets += 1
                logging.info(f"Deleted bucket {bucket}")
            else:
                logging.error(f"Failed to delete bucket {bucket}")
        del wasabi_bucket

    logging.info(f"Deleted {deleted_buckets} buckets, total size: {size_str}, total objects: {object_count:,}")


def main():
    """Main function."""
    logging.basicConfig(
        level=LOGLEVEL,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    delete_buckets(buckets_to_delete)


if __name__ == "__main__":
    main()
