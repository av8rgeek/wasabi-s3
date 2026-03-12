"""
Characterization tests for Bucket.
Documents current behavior as-is, including known quirks.
"""
import json
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from botocore.exceptions import ClientError

from wasabi.bucket import Bucket


@pytest.fixture
def mock_bucket(mock_boto3_client):
    """Create a Bucket with a mocked client where bucket does NOT exist."""
    mock_boto3_client.list_buckets.return_value = {"Buckets": []}
    mock_boto3_client.get_waiter.return_value = MagicMock()
    bucket = Bucket("test-bucket", region="us-east-1")
    return bucket, mock_boto3_client


@pytest.fixture
def mock_existing_bucket(mock_boto3_client):
    """Create a Bucket with a mocked client where bucket exists.
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
    bucket = Bucket("test-bucket", region="us-east-1", billing_data=billing_data)
    return bucket, mock_boto3_client


class TestBucketInit:
    """Document bucket initialization behavior."""

    def test_nonexistent_bucket_has_empty_properties(self, mock_bucket):
        bucket, _ = mock_bucket
        props = bucket.to_dict()
        assert props["name"] == "test-bucket"
        assert props["arn"] == "arn:aws:s3:::test-bucket"
        assert props["region"] == "us-east-1"
        assert props["bucket_policy"] == {}
        assert props["versioning"] is False

    def test_default_region_is_us_east_1(self, mock_boto3_client):
        mock_boto3_client.list_buckets.return_value = {"Buckets": []}
        bucket = Bucket("test-bucket")
        props = bucket.to_dict()
        assert props["region"] == "us-east-1"

    def test_existing_bucket_populates_properties(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        props = bucket.to_dict()
        assert props["name"] == "test-bucket"
        assert props["region"] == "us-east-1"
        assert props["bucket_policy"] == {}
        assert props["versioning"] is False

    def test_default_arg_billing_data_is_none(self, mock_boto3_client):
        """billing_data defaults to None to avoid mutable default arg bug."""
        import inspect
        sig = inspect.signature(Bucket.__init__)
        default = sig.parameters["billing_data"].default
        assert default is None


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
        """Returns empty dict on error."""
        bucket, client = mock_existing_bucket
        client.list_objects.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListObjects"
        )
        result = bucket.list_objects()
        assert result == {}

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

    def test_get_size_gb_from_billing_data(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [
            {
                "Bucket": "test-bucket",
                "PaddedStorageSizeBytes": 1073741824,  # 1 GB
                "MetadataStorageSizeBytes": 0,
                "DeletedStorageSizeBytes": 536870912,  # 0.5 GB
            }
        ]
        result = bucket.get_size_gb(billing_data=billing_data)
        assert result == 1.5

    def test_get_size_gb_returns_zero_when_not_found(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [{"Bucket": "other-bucket", "PaddedStorageSizeBytes": 0,
                         "MetadataStorageSizeBytes": 0, "DeletedStorageSizeBytes": 0}]
        result = bucket.get_size_gb(billing_data=billing_data)
        assert result == 0

    def test_get_object_count(self, mock_existing_bucket):
        bucket, _ = mock_existing_bucket
        billing_data = [
            {
                "Bucket": "test-bucket",
                "NumBillableObjects": 100,
                "NumBillableDeletedObjects": 20,
            }
        ]
        result = bucket.get_object_count(billing_data=billing_data)
        assert result == 120

    def test_default_arg_in_get_size_gb_is_none(self):
        """billing_data defaults to None to avoid mutable default arg bug."""
        import inspect
        sig = inspect.signature(Bucket.get_size_gb)
        default = sig.parameters["billing_data"].default
        assert default is None
