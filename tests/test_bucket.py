"""
Characterization tests for WasabiBucket.
Documents current behavior as-is, including known quirks.
"""
import json
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from botocore.exceptions import ClientError

from wasabi.bucket import WasabiBucket


@pytest.fixture
def mock_bucket(mock_boto3_client):
    """Create a WasabiBucket with a mocked client where bucket does NOT exist."""
    mock_boto3_client.list_buckets.return_value = {"Buckets": []}
    mock_boto3_client.get_waiter.return_value = MagicMock()
    bucket = WasabiBucket("test-bucket", region="us-east-1")
    return bucket, mock_boto3_client


@pytest.fixture
def mock_existing_bucket(mock_boto3_client):
    """Create a WasabiBucket with a mocked client where bucket exists.
    Passes billing_data to avoid hitting the real billing API."""
    mock_boto3_client.list_buckets.return_value = {
        "Buckets": [{"Name": "test-bucket"}]
    }
    mock_boto3_client.get_bucket_location.return_value = {
        "LocationConstraint": "us-east-1"
    }
    mock_boto3_client.get_bucket_policy.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucketPolicy", "Message": ""}}, "GetBucketPolicy"
    )
    mock_boto3_client.get_bucket_lifecycle_configuration.side_effect = ClientError(
        {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": ""}},
        "GetBucketLifecycleConfiguration",
    )
    mock_boto3_client.get_bucket_versioning.return_value = {}
    mock_boto3_client.get_waiter.return_value = MagicMock()
    billing_data = [
        {
            "Bucket": "test-bucket",
            "PaddedStorageSizeBytes": 0,
            "MetadataStorageSizeBytes": 0,
            "DeletedStorageSizeBytes": 0,
            "NumBillableObjects": 0,
            "NumBillableDeletedObjects": 0,
        }
    ]
    bucket = WasabiBucket("test-bucket", region="us-east-1", billing_data=billing_data)
    return bucket, mock_boto3_client


class TestBucketInit:
    """Document bucket initialization behavior."""

    def test_nonexistent_bucket_has_empty_properties(self, mock_bucket):
        bucket, _ = mock_bucket
        props = bucket.export_properties()
        assert props["name"] == "test-bucket"
        assert props["arn"] == "arn:aws:s3:::test-bucket"
        assert props["region"] == "us-east-1"
        assert props["bucket_policy"] == {}
        assert props["versioning"] is False

    def test_default_region_is_us_east_1(self, mock_boto3_client):
        mock_boto3_client.list_buckets.return_value = {"Buckets": []}
        bucket = WasabiBucket("test-bucket")
        props = bucket.export_properties()
        assert props["region"] == "us-east-1"

    def test_existing_bucket_populates_properties(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        props = bucket.export_properties()
        assert props["name"] == "test-bucket"
        assert props["region"] == "us-east-1"
        assert props["bucket_policy"] == {}
        assert props["versioning"] is False

    def test_mutable_default_arg_billing_data(self, mock_boto3_client):
        """Current behavior: mutable default dict={} in __init__ signature.
        This is a known bug — shared across all calls."""
        import inspect
        sig = inspect.signature(WasabiBucket.__init__)
        default = sig.parameters["billing_data"].default
        assert default == {}
        assert isinstance(default, dict)


class TestBucketExists:
    """Document bucket_exists behavior."""

    def test_returns_true_when_found(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        assert bucket.bucket_exists() is True

    def test_returns_false_when_not_found(self, mock_bucket):
        bucket, _ = mock_bucket
        assert bucket.bucket_exists() is False


class TestBucketCRUD:
    """Document create/delete bucket behavior."""

    def test_create_bucket_when_not_exists(self, mock_bucket):
        bucket, client = mock_bucket
        client.create_bucket.return_value = {}
        client.get_bucket_location.return_value = {"LocationConstraint": "us-east-1"}
        result = bucket.create_bucket()
        assert result is True
        client.create_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_create_bucket_when_already_exists(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.create_bucket()
        assert result is False
        client.create_bucket.assert_not_called()

    def test_delete_bucket_when_exists(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.delete_bucket()
        assert result is True
        client.delete_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_delete_bucket_when_not_exists_returns_true(self, mock_bucket):
        """Current behavior: returns True if bucket doesn't exist (skip)."""
        bucket, _ = mock_bucket
        result = bucket.delete_bucket()
        assert result is True

    def test_delete_bucket_not_empty_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.delete_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketNotEmpty", "Message": "not empty"}},
            "DeleteBucket",
        )
        result = bucket.delete_bucket()
        assert result is False


class TestBucketPolicy:
    """Document bucket policy retrieval."""

    def test_returns_parsed_policy_dict(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        policy_doc = {"Version": "2012-10-17", "Statement": []}
        client.get_bucket_policy.side_effect = None
        client.get_bucket_policy.return_value = {"Policy": json.dumps(policy_doc)}
        result = bucket.get_bucket_policy()
        assert result == policy_doc

    def test_returns_empty_dict_when_no_policy(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        result = bucket.get_bucket_policy()
        assert result == {}


class TestBucketVersioning:
    """Document versioning status retrieval."""

    def test_returns_true_when_enabled(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_versioning.return_value = {"Status": "Enabled"}
        assert bucket.get_versioning() is True

    def test_returns_false_when_suspended(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_versioning.return_value = {"Status": "Suspended"}
        assert bucket.get_versioning() is False

    def test_returns_false_when_no_status_key(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_versioning.return_value = {}
        assert bucket.get_versioning() is False


class TestBucketObjects:
    """Document object operations."""

    def test_list_objects_returns_response(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.list_objects.return_value = {"Contents": [{"Key": "file.txt"}]}
        result = bucket.list_objects()
        assert "Contents" in result

    def test_list_objects_returns_none_on_error(self, mock_existing_bucket):
        """Current behavior: returns None on error, not empty dict."""
        bucket, client = mock_existing_bucket
        client.list_objects.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListObjects"
        )
        result = bucket.list_objects()
        assert result is None

    def test_put_object_returns_true_on_success(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.put_object(key="test.txt", body="hello")
        assert result is True

    def test_delete_object_returns_true_on_success(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.delete_object(key="test.txt")
        assert result is True


class TestBucketBillingMetrics:
    """Document billing-based size/count methods."""

    def test_get_bucket_size_gb_from_billing_data(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [
            {
                "Bucket": "test-bucket",
                "PaddedStorageSizeBytes": 1073741824,  # 1 GB
                "MetadataStorageSizeBytes": 0,
                "DeletedStorageSizeBytes": 536870912,  # 0.5 GB
            }
        ]
        result = bucket.get_bucket_size_gb(billing_data=billing_data)
        assert result == 1.5

    def test_get_bucket_size_gb_returns_zero_when_not_found(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [{"Bucket": "other-bucket", "PaddedStorageSizeBytes": 0,
                         "MetadataStorageSizeBytes": 0, "DeletedStorageSizeBytes": 0}]
        result = bucket.get_bucket_size_gb(billing_data=billing_data)
        assert result == 0

    def test_get_bucket_object_count(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [
            {
                "Bucket": "test-bucket",
                "NumBillableObjects": 100,
                "NumBillableDeletedObjects": 20,
            }
        ]
        result = bucket.get_bucket_object_count(billing_data=billing_data)
        assert result == 120

    def test_mutable_default_arg_in_get_bucket_size_gb(self):
        """Current behavior: mutable default dict={} in signature."""
        import inspect
        sig = inspect.signature(WasabiBucket.get_bucket_size_gb)
        default = sig.parameters["billing_data"].default
        assert default == {}
        assert isinstance(default, dict)
