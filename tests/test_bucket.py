"""
Characterization tests for Bucket.
Documents current behavior as-is, including known quirks.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from wasabi_s3.bucket import Bucket


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


def _client_error(code, message="error"):
    return ClientError({"Error": {"Code": code, "Message": message}}, "op")


class TestSetVersioning:
    """Document set_versioning behavior."""

    def test_enable_versioning_returns_true(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.set_versioning(True)
        assert result is True
        client.put_bucket_versioning.assert_called_once_with(
            Bucket="test-bucket",
            VersioningConfiguration={"Status": "Enabled"},
        )

    def test_suspend_versioning_returns_true(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.set_versioning(False)
        assert result is True
        client.put_bucket_versioning.assert_called_once_with(
            Bucket="test-bucket",
            VersioningConfiguration={"Status": "Suspended"},
        )

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.put_bucket_versioning.side_effect = _client_error("InternalError")
        result = bucket.set_versioning(True)
        assert result is False


class TestSetLifecycle:
    """Document set_lifecycle behavior."""

    def test_success_returns_true(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        rules = {"Rules": [{"Status": "Enabled", "Prefix": "", "Expiration": {"Days": 30}}]}
        result = bucket.set_lifecycle(rules)
        assert result is True
        client.put_bucket_lifecycle_configuration.assert_called_once_with(
            Bucket="test-bucket",
            LifecycleConfiguration=rules,
        )

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.put_bucket_lifecycle_configuration.side_effect = _client_error("MalformedXML")
        result = bucket.set_lifecycle({"Rules": []})
        assert result is False


class TestSetBucketPolicy:
    """Document set_bucket_policy behavior."""

    def test_success_returns_true(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        policy = {"Version": "2012-10-17", "Statement": []}
        result = bucket.set_bucket_policy(policy)
        assert result is True
        client.put_bucket_policy.assert_called_once_with(
            Bucket="test-bucket",
            Policy=json.dumps(policy),
        )

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.put_bucket_policy.side_effect = _client_error("MalformedPolicy")
        result = bucket.set_bucket_policy({"Version": "2012-10-17", "Statement": []})
        assert result is False


class TestDeleteBucketPolicy:
    """Document delete_bucket_policy behavior."""

    def test_success_returns_true(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        result = bucket.delete_bucket_policy()
        assert result is True
        client.delete_bucket_policy.assert_called_once_with(Bucket="test-bucket")

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.delete_bucket_policy.side_effect = _client_error("AccessDenied")
        result = bucket.delete_bucket_policy()
        assert result is False


class TestForceDeleteBucket:
    """Document force_delete_bucket behavior."""

    def test_not_exists_returns_true(self, mock_bucket):
        """When the bucket does not exist, returns True (skip)."""
        bucket, _ = mock_bucket
        result = bucket.force_delete_bucket()
        assert result is True

    @patch("wasabi_s3.bucket.requests.delete")
    def test_success_204_returns_true(self, mock_requests_delete, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_requests_delete.return_value = mock_response
        result = bucket.force_delete_bucket()
        assert result is True
        mock_requests_delete.assert_called_once()

    @patch("wasabi_s3.bucket.requests.delete")
    def test_non_204_returns_false(self, mock_requests_delete, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_requests_delete.return_value = mock_response
        result = bucket.force_delete_bucket()
        assert result is False

    @patch("wasabi_s3.bucket.requests.delete")
    def test_client_error_returns_false(self, mock_requests_delete, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        mock_requests_delete.side_effect = _client_error("InternalError")
        result = bucket.force_delete_bucket()
        assert result is False


class TestPutObjectError:
    """Document put_object error path."""

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.put_object.side_effect = _client_error("AccessDenied")
        result = bucket.put_object(key="test.txt", body="hello")
        assert result is False


class TestDeleteObjectError:
    """Document delete_object error path."""

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.delete_object.side_effect = _client_error("AccessDenied")
        result = bucket.delete_object(key="test.txt")
        assert result is False


class TestCreateBucketClientError:
    """Document create_bucket ClientError path."""

    def test_client_error_returns_false(self, mock_bucket):
        bucket, client = mock_bucket
        client.create_bucket.side_effect = _client_error("BucketAlreadyExists")
        result = bucket.create_bucket()
        assert result is False


class TestGetVersioningClientError:
    """Document get_versioning ClientError path."""

    def test_client_error_returns_false(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_versioning.side_effect = _client_error("InternalError")
        result = bucket.get_versioning()
        assert result is False


class TestGetLifecycle:
    """Document get_lifecycle behavior."""

    def test_returns_dict_on_success(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        lifecycle_config = {
            "Rules": [{"Status": "Enabled", "Prefix": "", "Expiration": {"Days": 30}}]
        }
        client.get_bucket_lifecycle_configuration.side_effect = None
        client.get_bucket_lifecycle_configuration.return_value = lifecycle_config
        result = bucket.get_lifecycle()
        assert result == lifecycle_config

    def test_returns_empty_dict_on_no_such_lifecycle(self, mock_existing_bucket):
        """NoSuchLifecycleConfiguration is handled gracefully."""
        bucket, client = mock_existing_bucket
        client.get_bucket_lifecycle_configuration.side_effect = ClientError(
            {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": ""}},
            "GetBucketLifecycleConfiguration",
        )
        result = bucket.get_lifecycle()
        assert result == {}


class TestUpdateProperties:
    """Document update_properties behavior."""

    def test_updates_properties_when_bucket_exists(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        # Set up return values for the refresh calls
        client.get_bucket_location.return_value = {"LocationConstraint": "us-east-1"}
        client.get_bucket_policy.side_effect = None
        policy_doc = {"Version": "2012-10-17", "Statement": []}
        client.get_bucket_policy.return_value = {"Policy": json.dumps(policy_doc)}
        client.get_bucket_lifecycle_configuration.side_effect = None
        lifecycle_config = {"Rules": [{"Status": "Enabled"}]}
        client.get_bucket_lifecycle_configuration.return_value = lifecycle_config
        client.get_bucket_versioning.return_value = {"Status": "Enabled"}

        bucket.update_properties()

        props = bucket.to_dict()
        assert props["region"] == "us-east-1"
        assert props["bucket_policy"] == policy_doc
        assert props["lifecycle-rules"] == lifecycle_config
        assert props["versioning"] is True

    def test_no_update_when_bucket_does_not_exist(self, mock_bucket):
        """When the bucket does not exist, properties remain unchanged."""
        bucket, client = mock_bucket
        original_props = bucket.to_dict().copy()
        bucket.update_properties()
        assert bucket.to_dict() == original_props


class TestBucketConstructorValidation:
    """Document constructor validation behavior."""

    def test_empty_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="bucket_name must be a non-empty string"):
            Bucket("")

    def test_whitespace_only_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="bucket_name must be a non-empty string"):
            Bucket("   ")

    def test_non_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="bucket_name must be a non-empty string"):
            Bucket(123)


class TestBucketInvalidS3Region:
    """Document behavior when a non-S3 region is passed."""

    def test_non_s3_endpoint_logs_exception(self, mock_boto3_client):
        """Passing 'iam' is a valid Endpoint but not an S3 endpoint."""
        mock_boto3_client.list_buckets.return_value = {"Buckets": []}
        bucket = Bucket("test-bucket", region="iam")
        # Constructor completes but endpoint attribute was never set
        assert bucket.bucket_name == "test-bucket"


class TestGetBucketLocationBranches:
    """Document get_bucket_location branch coverage."""

    def test_location_constraint_none_returns_us_east_1(self, mock_existing_bucket):
        """Wasabi returns None for us-east-1 (AWS SDK quirk)."""
        bucket, client = mock_existing_bucket
        client.get_bucket_location.return_value = {"LocationConstraint": None}
        result = bucket.get_bucket_location()
        assert result == "us-east-1"

    def test_location_differs_from_properties_corrects_region(self, mock_existing_bucket):
        """When location differs from stored region, corrects the property."""
        bucket, client = mock_existing_bucket
        client.get_bucket_location.return_value = {"LocationConstraint": "us-west-1"}
        result = bucket.get_bucket_location()
        assert result == "us-west-1"
        assert bucket.to_dict()["region"] == "us-west-1"

    def test_client_error_returns_empty_string(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_location.side_effect = _client_error("AccessDenied")
        result = bucket.get_bucket_location()
        assert result == ""


class TestGetBucketPolicyNonStandardError:
    """Document get_bucket_policy on non-NoSuchBucketPolicy errors."""

    def test_non_nosuchbucketpolicy_error_returns_empty_dict(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_policy.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "forbidden"}},
            "GetBucketPolicy",
        )
        result = bucket.get_bucket_policy()
        assert result == {}


class TestGetLifecycleNonStandardError:
    """Document get_lifecycle on non-NoSuchLifecycleConfiguration errors."""

    def test_non_standard_error_returns_empty_dict(self, mock_existing_bucket):
        bucket, client = mock_existing_bucket
        client.get_bucket_lifecycle_configuration.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "forbidden"}},
            "GetBucketLifecycleConfiguration",
        )
        result = bucket.get_lifecycle()
        assert result == {}


class TestGetSizeGbNoBillingData:
    """Document get_size_gb when no billing_data is passed and none cached."""

    @patch.object(Bucket, "get_billing_data")
    def test_fetches_billing_data_when_not_cached(self, mock_get_billing, mock_bucket):
        bucket, _ = mock_bucket
        mock_get_billing.return_value = [
            {
                "Bucket": "test-bucket",
                "PaddedStorageSizeBytes": 1073741824,
                "MetadataStorageSizeBytes": 0,
                "DeletedStorageSizeBytes": 0,
            }
        ]
        result = bucket.get_size_gb()
        assert result == 1.0
        mock_get_billing.assert_called_once()


class TestGetObjectCountNoBillingData:
    """Document get_object_count when no billing_data is passed and none cached."""

    @patch.object(Bucket, "get_billing_data")
    def test_fetches_billing_data_when_not_cached(self, mock_get_billing, mock_bucket):
        bucket, _ = mock_bucket
        mock_get_billing.return_value = [
            {
                "Bucket": "test-bucket",
                "NumBillableObjects": 50,
                "NumBillableDeletedObjects": 10,
            }
        ]
        result = bucket.get_object_count()
        assert result == 60
        mock_get_billing.assert_called_once()
