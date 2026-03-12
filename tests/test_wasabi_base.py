"""
Characterization tests for the base Wasabi class and supporting classes.
Documents current behavior as-is, including known quirks.
"""
import json
from datetime import datetime, date, timezone
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from wasabi.wasabi import Wasabi, WasabiEndpoints, DateTimeEncoder, WasabiBillingApiAuthorization


class TestWasabiEndpoints:
    """Document current endpoint enum behavior."""

    def test_s3_endpoint_value(self):
        assert WasabiEndpoints.S3.value == "https://s3.wasabisys.com"

    def test_us_east_1_value(self):
        assert WasabiEndpoints.US_EAST_1.value == "https://s3.us-east-1.wasabisys.com"

    def test_iam_endpoint_value(self):
        assert WasabiEndpoints.IAM.value == "https://iam.wasabisys.com"

    def test_sts_endpoint_value(self):
        assert WasabiEndpoints.STS.value == "https://sts.wasabisys.com"

    def test_billing_endpoint_value(self):
        assert WasabiEndpoints.BILLING.value == "https://billing.wasabisys.com"

    def test_to_lower_converts_underscores_to_hyphens(self):
        assert WasabiEndpoints.to_lower("US_EAST_1") == "us-east-1"

    def test_to_upper_converts_hyphens_to_underscores(self):
        assert WasabiEndpoints.to_upper("us-east-1") == "US_EAST_1"

    def test_to_lower_empty_string(self):
        assert WasabiEndpoints.to_lower("") == ""

    def test_to_upper_empty_string(self):
        assert WasabiEndpoints.to_upper("") == ""

    def test_s3_endpoints_list_length(self):
        assert len(WasabiEndpoints.S3_ENDPOINTS) == 15

    def test_s3_endpoints_contains_primary(self):
        assert WasabiEndpoints.S3.value in WasabiEndpoints.S3_ENDPOINTS

    def test_s3_endpoints_does_not_contain_iam(self):
        assert WasabiEndpoints.IAM.value not in WasabiEndpoints.S3_ENDPOINTS

    def test_s3_endpoints_does_not_contain_sts(self):
        assert WasabiEndpoints.STS.value not in WasabiEndpoints.S3_ENDPOINTS

    def test_s3_endpoints_does_not_contain_billing(self):
        assert WasabiEndpoints.BILLING.value not in WasabiEndpoints.S3_ENDPOINTS


class TestDateTimeEncoder:
    """Document current JSON encoding behavior."""

    def test_encodes_datetime_to_isoformat(self):
        dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        result = json.dumps({"ts": dt}, cls=DateTimeEncoder)
        assert '"2024-01-15T12:30:00+00:00"' in result

    def test_encodes_date_to_isoformat(self):
        d = date(2024, 1, 15)
        result = json.dumps({"d": d}, cls=DateTimeEncoder)
        assert '"2024-01-15"' in result

    def test_non_date_returns_none(self):
        """Current behavior: returns None for non-date types instead of raising.
        This is a known bug — should call super().default(obj)."""
        encoder = DateTimeEncoder()
        result = encoder.default({"not": "a date"})
        assert result is None


class TestWasabiInit:
    """Document base Wasabi class initialization."""

    def test_reads_credentials_from_env(self):
        w = Wasabi()
        assert w.aws_access_key_id == "test-access-key"
        assert w.aws_secret_access_key == "test-secret-key"

    def test_credentials_are_public_attributes(self):
        """Current behavior: credentials are public. Documented for refactor."""
        w = Wasabi()
        assert hasattr(w, "aws_access_key_id")
        assert hasattr(w, "aws_secret_access_key")

    def test_missing_credentials_are_none(self, monkeypatch):
        """Current behavior: getenv returns None when unset, not empty string."""
        monkeypatch.delenv("WASABI_ACCESS_KEY")
        monkeypatch.delenv("WASABI_SECRET_KEY")
        w = Wasabi()
        assert w.aws_access_key_id is None
        assert w.aws_secret_access_key is None

    def test_default_request_timeout(self):
        w = Wasabi()
        assert w.request_timeout == 30

    def test_iam_region_value(self):
        w = Wasabi()
        assert w.iam_region == "iam"

    def test_sts_region_value(self):
        w = Wasabi()
        assert w.sts_region == "sts"

    def test_billing_data_starts_empty(self):
        w = Wasabi()
        assert w._billing_data == {}

    def test_get_example_schema_returns_string(self):
        w = Wasabi()
        schema = w.get_example_schema()
        assert isinstance(schema, str)
        assert '"users"' in schema
        assert '"buckets"' in schema


class TestWasabiNewClient:
    """Document _new_client behavior."""

    def test_valid_s3_region_creates_client(self, mock_boto3_client):
        w = Wasabi()
        client = w._new_client("us-east-1")
        assert client is not None

    def test_s3_region_remaps_to_us_east_1(self, mock_boto3_client):
        """'s3' is a special alias that maps to us-east-1 region."""
        w = Wasabi()
        import boto3
        w._new_client("s3")
        call_kwargs = boto3.client.call_args
        assert call_kwargs[1]["region_name"] == "us-east-1"

    def test_iam_region_remaps_to_us_east_1(self, mock_boto3_client):
        w = Wasabi()
        import boto3
        w._new_client("iam")
        call_kwargs = boto3.client.call_args
        assert call_kwargs[1]["region_name"] == "us-east-1"

    def test_invalid_region_raises_exception(self):
        w = Wasabi()
        with pytest.raises(Exception, match="Invalid Wasabi region"):
            w._new_client("invalid-region")

    def test_billing_region_raises_valueerror(self, mock_boto3_client):
        w = Wasabi()
        with pytest.raises(ValueError, match="Billing API does not use a boto3 client"):
            w._new_client("billing")

    def test_assert_on_empty_credentials(self, monkeypatch, mock_boto3_client):
        """Current behavior: uses assert for validation, which can be stripped with -O."""
        monkeypatch.setenv("WASABI_ACCESS_KEY", "")
        monkeypatch.setenv("WASABI_SECRET_KEY", "")
        w = Wasabi()
        with pytest.raises(AssertionError, match="Missing Wasabi credentials"):
            w._new_client("us-east-1")


class TestWasabiGetBuckets:
    """Document get_buckets behavior."""

    def test_returns_dict_of_name_to_location(self, mock_boto3_client):
        mock_boto3_client.list_buckets.return_value = {
            "Buckets": [
                {"Name": "bucket-a", "CreationDate": "2024-01-01"},
                {"Name": "bucket-b", "CreationDate": "2024-01-02"},
            ]
        }
        mock_boto3_client.get_bucket_location.side_effect = [
            {"LocationConstraint": None},
            {"LocationConstraint": "eu-west-1"},
        ]
        w = Wasabi()
        result = w.get_buckets()
        assert result == {"bucket-a": "us-east-1", "bucket-b": "eu-west-1"}


class TestWasabiGetManagedPolicies:
    """Document get_managed_policies behavior."""

    def test_returns_policies_list(self, mock_boto3_client):
        mock_boto3_client.list_policies.return_value = {
            "Policies": [{"PolicyName": "my-policy", "Arn": "arn:aws:iam::123:policy/my-policy"}]
        }
        w = Wasabi()
        result = w.get_managed_policies()
        assert len(result) == 1
        assert result[0]["PolicyName"] == "my-policy"

    def test_returns_empty_list_on_error(self, mock_boto3_client):
        mock_boto3_client.list_policies.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListPolicies"
        )
        w = Wasabi()
        result = w.get_managed_policies()
        assert result == []


class TestWasabiGetGroups:
    """Document get_groups behavior."""

    def test_returns_groups_list(self, mock_boto3_client):
        mock_boto3_client.list_groups.return_value = {
            "Groups": [{"GroupName": "admins", "Arn": "arn:aws:iam::123:group/admins"}]
        }
        w = Wasabi()
        result = w.get_groups()
        assert len(result) == 1

    def test_returns_empty_list_on_error(self, mock_boto3_client):
        mock_boto3_client.list_groups.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListGroups"
        )
        w = Wasabi()
        result = w.get_groups()
        assert result == []


class TestWasabiGetUsers:
    """Document get_users behavior."""

    def test_returns_users_list(self, mock_boto3_client):
        mock_boto3_client.list_users.return_value = {
            "Users": [{"UserName": "alice", "Arn": "arn:aws:iam::123:user/alice"}]
        }
        w = Wasabi()
        result = w.get_users()
        assert len(result) == 1

    def test_returns_empty_list_on_error(self, mock_boto3_client):
        mock_boto3_client.list_users.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}}, "ListUsers"
        )
        w = Wasabi()
        result = w.get_users()
        assert result == []


class TestWasabiBillingApiAuthorization:
    """Document billing auth header format."""

    def test_sets_authorization_header(self):
        creds = {"id": "my-key", "secret": "my-secret"}
        auth = WasabiBillingApiAuthorization(creds)
        request = MagicMock()
        request.headers = {}
        result = auth(request)
        assert result.headers["Authorization"] == "my-key:my-secret"
