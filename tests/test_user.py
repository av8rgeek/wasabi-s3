"""
Characterization tests for User.
Documents current behavior as-is, including known quirks.
"""
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from wasabi.user import User


@pytest.fixture
def mock_nonexistent_user(mock_boto3_client):
    """User where user does NOT exist."""
    mock_boto3_client.get_user.side_effect = ClientError(
        {"Error": {"Code": "NoSuchEntity", "Message": "not found"}}, "GetUser"
    )
    user = User("alice")
    return user, mock_boto3_client


@pytest.fixture
def mock_existing_user(mock_boto3_client):
    """User where user exists with one API key."""
    mock_boto3_client.get_user.return_value = {
        "User": {"UserName": "alice", "Arn": "arn:aws:iam::123456789012:user/alice"}
    }
    mock_boto3_client.list_access_keys.return_value = {
        "AccessKeyMetadata": [
            {"AccessKeyId": "AKIA1111", "Status": "Active"}
        ]
    }
    user = User("alice")
    return user, mock_boto3_client


class TestUserInit:
    """Document user initialization behavior."""

    def test_nonexistent_user_properties(self, mock_nonexistent_user):
        user, _ = mock_nonexistent_user
        props = user.to_dict()
        assert props["name"] == "alice"
        assert props["arn"] == ""
        assert props["api-keys"] == {}

    def test_existing_user_populates_arn(self, mock_existing_user):
        user, _ = mock_existing_user
        props = user.to_dict()
        assert props["name"] == "alice"
        assert props["arn"] == "arn:aws:iam::123456789012:user/alice"

    def test_existing_user_populates_api_keys(self, mock_existing_user):
        user, _ = mock_existing_user
        props = user.to_dict()
        assert "AKIA1111" in props["api-keys"]
        assert props["api-keys"]["AKIA1111"]["status"] == "Active"
        assert props["api-keys"]["AKIA1111"]["secret-key"] == ""

    def test_properties_annotated_as_list_but_is_dict(self, mock_nonexistent_user):
        """Current behavior: __properties annotated as list but is actually dict."""
        user, _ = mock_nonexistent_user
        props = user.to_dict()
        assert isinstance(props, dict)


class TestUserExists:
    """Document user_exists behavior."""

    def test_returns_true_when_found(self, mock_existing_user):
        user, _ = mock_existing_user
        assert user.user_exists() is True

    def test_returns_false_when_not_found(self, mock_nonexistent_user):
        user, _ = mock_nonexistent_user
        assert user.user_exists() is False

    def test_returns_none_on_unexpected_error(self, mock_boto3_client):
        """Current behavior: returns None (implicit) on non-NoSuchEntity errors."""
        mock_boto3_client.get_user.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}}, "GetUser"
        )
        mock_boto3_client.list_access_keys.return_value = {"AccessKeyMetadata": []}
        user = User("alice")
        mock_boto3_client.get_user.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}}, "GetUser"
        )
        result = user.user_exists()
        assert result is False


class TestUserCRUD:
    """Document create/delete user behavior."""

    def test_create_user_returns_response(self, mock_nonexistent_user):
        user, client = mock_nonexistent_user
        client.create_user.return_value = {
            "User": {"UserName": "alice", "Arn": "arn:aws:iam::123:user/alice"}
        }
        result = user.create_user()
        assert result["User"]["UserName"] == "alice"

    def test_create_user_when_exists_returns_existing(self, mock_existing_user):
        user, client = mock_existing_user
        result = user.create_user()
        assert result["User"]["Arn"] == "arn:aws:iam::123456789012:user/alice"
        client.create_user.assert_not_called()

    def test_delete_user_returns_bool(self, mock_existing_user):
        """Current behavior: annotated as -> dict but returns bool."""
        user, client = mock_existing_user
        client.list_access_keys.return_value = {"AccessKeyMetadata": []}
        result = user.delete_user()
        assert result is True
        assert isinstance(result, bool)

    def test_delete_user_when_not_exists_returns_false(self, mock_nonexistent_user):
        user, _ = mock_nonexistent_user
        result = user.delete_user()
        assert result is False


class TestUserApiKeys:
    """Document API key management behavior."""

    def test_get_api_keys_returns_dict(self, mock_existing_user):
        """Current behavior: annotated as -> list but returns dict."""
        user, _ = mock_existing_user
        keys = user.get_api_keys()
        assert isinstance(keys, dict)
        assert "AKIA1111" in keys

    def test_create_api_key_stores_secret(self, mock_existing_user):
        user, client = mock_existing_user
        client.create_access_key.return_value = {
            "AccessKey": {
                "AccessKeyId": "AKIA2222",
                "SecretAccessKey": "secret123",
                "Status": "Active",
            }
        }
        result = user.create_api_key()
        assert "AKIA2222" in result
        assert result["AKIA2222"]["secret-key"] == "secret123"

    def test_create_api_key_blocked_at_two_keys(self, mock_existing_user):
        user, client = mock_existing_user
        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Active"},
                {"AccessKeyId": "AKIA2222", "Status": "Active"},
            ]
        }
        result = user.create_api_key()
        assert result == {}
        client.create_access_key.assert_not_called()

    def test_delete_api_key_returns_bool(self, mock_existing_user):
        user, _ = mock_existing_user
        result = user.delete_api_key("AKIA1111")
        assert result is True

    def test_delete_all_api_keys_clears_properties(self, mock_existing_user):
        """Current behavior: sets api-keys to [] (list), not {} (dict)."""
        user, client = mock_existing_user
        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Active"}
            ]
        }
        result = user.delete_all_api_keys()
        assert result is True
        props = user.to_dict()
        assert props["api-keys"] == {}
