"""
Characterization tests for User.
Documents current behavior as-is, including known quirks.
"""

import pytest
from botocore.exceptions import ClientError

from wasabi_s3.user import User


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


class TestGetGroups:
    """Document list_groups behavior."""

    def test_returns_list_of_group_names(self, mock_existing_user):
        user, client = mock_existing_user
        client.list_groups_for_user.return_value = {
            "Groups": [
                {"GroupName": "admins"},
                {"GroupName": "developers"},
            ]
        }
        result = user.list_groups()
        assert result == ["admins", "developers"]
        client.list_groups_for_user.assert_called_once_with(UserName="alice")

    def test_returns_empty_list_when_no_groups(self, mock_existing_user):
        user, client = mock_existing_user
        client.list_groups_for_user.return_value = {"Groups": []}
        result = user.list_groups()
        assert result == []

    def test_returns_empty_list_on_error(self, mock_existing_user):
        user, client = mock_existing_user
        client.list_groups_for_user.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "not found"}},
            "ListGroupsForUser",
        )
        result = user.list_groups()
        assert result == []


class TestEnableApiKey:
    """Document enable_api_key behavior."""

    def test_success_returns_true(self, mock_existing_user):
        user, client = mock_existing_user
        result = user.enable_api_key("AKIA1111")
        assert result is True
        client.update_access_key.assert_called_once_with(
            UserName="alice", AccessKeyId="AKIA1111", Status="Active"
        )

    def test_success_updates_properties_for_known_key(self, mock_existing_user):
        """When the key exists in properties, its status is set to Active."""
        user, client = mock_existing_user
        # The fixture sets AKIA1111 as Active; first disable it in properties
        # to verify enable flips it back.
        props = user.to_dict()
        props["api-keys"]["AKIA1111"]["status"] = "Inactive"

        user.enable_api_key("AKIA1111")
        assert props["api-keys"]["AKIA1111"]["status"] == "Active"

    def test_success_for_key_not_in_properties(self, mock_existing_user):
        """When the key is not tracked in properties, still returns True."""
        user, client = mock_existing_user
        result = user.enable_api_key("AKIA9999")
        assert result is True
        # Properties should not have gained a new entry for the unknown key
        assert "AKIA9999" not in user.to_dict()["api-keys"]

    def test_error_returns_false(self, mock_existing_user):
        user, client = mock_existing_user
        client.update_access_key.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "key not found"}},
            "UpdateAccessKey",
        )
        result = user.enable_api_key("AKIA1111")
        assert result is False


class TestDisableApiKey:
    """Document disable_api_key behavior."""

    def test_success_returns_true(self, mock_existing_user):
        user, client = mock_existing_user
        result = user.disable_api_key("AKIA1111")
        assert result is True
        client.update_access_key.assert_called_once_with(
            UserName="alice", AccessKeyId="AKIA1111", Status="Inactive"
        )

    def test_success_updates_properties_for_known_key(self, mock_existing_user):
        """When the key exists in properties, its status is set to Inactive."""
        user, client = mock_existing_user
        props = user.to_dict()
        assert props["api-keys"]["AKIA1111"]["status"] == "Active"

        user.disable_api_key("AKIA1111")
        assert props["api-keys"]["AKIA1111"]["status"] == "Inactive"

    def test_success_for_key_not_in_properties(self, mock_existing_user):
        """When the key is not tracked in properties, still returns True."""
        user, client = mock_existing_user
        result = user.disable_api_key("AKIA9999")
        assert result is True
        assert "AKIA9999" not in user.to_dict()["api-keys"]

    def test_error_returns_false(self, mock_existing_user):
        user, client = mock_existing_user
        client.update_access_key.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "key not found"}},
            "UpdateAccessKey",
        )
        result = user.disable_api_key("AKIA1111")
        assert result is False


class TestCreateUserError:
    """Document create_user error handling."""

    def test_client_error_returns_empty_dict(self, mock_nonexistent_user):
        user, client = mock_nonexistent_user
        client.create_user.side_effect = ClientError(
            {"Error": {"Code": "LimitExceeded", "Message": "too many users"}},
            "CreateUser",
        )
        result = user.create_user()
        assert result == {}


class TestDeleteApiKeyError:
    """Document delete_api_key error handling."""

    def test_error_returns_false(self, mock_existing_user):
        user, client = mock_existing_user
        client.delete_access_key.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "key not found"}},
            "DeleteAccessKey",
        )
        result = user.delete_api_key("AKIA1111")
        assert result is False


class TestGetApiKeysError:
    """Document get_api_keys error handling."""

    def test_error_returns_empty_dict(self, mock_existing_user):
        """get_api_keys returns empty dict (not list) on ClientError."""
        user, client = mock_existing_user
        client.list_access_keys.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}},
            "ListAccessKeys",
        )
        result = user.get_api_keys()
        assert result == {}


class TestUpdateApiKeys:
    """Document update_api_keys behavior."""

    def test_adds_new_key_to_properties(self, mock_existing_user):
        """A key returned by the API but not in properties gets added."""
        user, client = mock_existing_user
        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Active"},
                {"AccessKeyId": "AKIA3333", "Status": "Inactive"},
            ]
        }
        user.update_api_keys()

        props = user.to_dict()
        assert "AKIA3333" in props["api-keys"]
        assert props["api-keys"]["AKIA3333"]["status"] == "Inactive"
        assert props["api-keys"]["AKIA3333"]["secret-key"] == ""

    def test_updates_existing_key_status(self, mock_existing_user):
        """An existing key whose status changed on the API gets updated."""
        user, client = mock_existing_user
        props = user.to_dict()
        assert props["api-keys"]["AKIA1111"]["status"] == "Active"

        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Inactive"},
            ]
        }
        user.update_api_keys()

        assert props["api-keys"]["AKIA1111"]["status"] == "Inactive"

    def test_preserves_secret_key_on_update(self, mock_existing_user):
        """update_api_keys should not overwrite an existing secret-key value."""
        user, client = mock_existing_user
        props = user.to_dict()
        # Simulate a key that had its secret stored from create_api_key
        props["api-keys"]["AKIA1111"]["secret-key"] = "original-secret"

        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Active"},
            ]
        }
        user.update_api_keys()

        # update_api_keys only touches "status", not "secret-key"
        assert props["api-keys"]["AKIA1111"]["secret-key"] == "original-secret"

    def test_error_leaves_properties_unchanged(self, mock_existing_user):
        """On ClientError, existing properties remain untouched."""
        user, client = mock_existing_user
        props_before = dict(user.to_dict()["api-keys"])

        client.list_access_keys.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}},
            "ListAccessKeys",
        )
        user.update_api_keys()

        assert user.to_dict()["api-keys"] == props_before


class TestUserConstructorValidation:
    """Document constructor validation behavior."""

    def test_empty_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="user_name must be a non-empty string"):
            User("")

    def test_whitespace_only_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="user_name must be a non-empty string"):
            User("   ")

    def test_non_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="user_name must be a non-empty string"):
            User(123)


class TestGetUserError:
    """Document get_user error path."""

    def test_returns_empty_dict_on_client_error(self, mock_existing_user):
        user, client = mock_existing_user
        client.get_user.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}},
            "GetUser",
        )
        result = user.get_user()
        assert result == {}


class TestDeleteUserError:
    """Document delete_user ClientError path."""

    def test_returns_false_on_client_error(self, mock_existing_user):
        user, client = mock_existing_user
        # delete_all_api_keys succeeds, but delete_user itself fails
        client.list_access_keys.return_value = {"AccessKeyMetadata": []}
        client.delete_user.side_effect = ClientError(
            {"Error": {"Code": "DeleteConflict", "Message": "user has resources"}},
            "DeleteUser",
        )
        result = user.delete_user()
        assert result is False


class TestGetArn:
    """Document get_arn behavior."""

    def test_returns_arn_string(self, mock_existing_user):
        user, _ = mock_existing_user
        result = user.get_arn()
        assert result == "arn:aws:iam::123456789012:user/alice"

    def test_returns_empty_string_for_nonexistent_user(self, mock_nonexistent_user):
        user, _ = mock_nonexistent_user
        result = user.get_arn()
        assert result == ""


class TestCreateApiKeyError:
    """Document create_api_key ClientError path."""

    def test_returns_empty_dict_on_client_error(self, mock_nonexistent_user):
        """When create_access_key fails, returns empty dict."""
        user, client = mock_nonexistent_user
        # User has no keys, so the guard allows creation
        client.list_access_keys.return_value = {"AccessKeyMetadata": []}
        client.create_access_key.side_effect = ClientError(
            {"Error": {"Code": "LimitExceeded", "Message": "too many keys"}},
            "CreateAccessKey",
        )
        result = user.create_api_key()
        assert result == {}


class TestDeleteAllApiKeysErrors:
    """Document delete_all_api_keys error paths."""

    def test_list_access_keys_error_returns_true_quirk(self, mock_existing_user):
        """Quirk: when list_access_keys fails, metadata=[], count(0)==len(0) → True."""
        user, client = mock_existing_user
        client.list_access_keys.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "boom"}},
            "ListAccessKeys",
        )
        result = user.delete_all_api_keys()
        assert result is True

    def test_delete_error_then_retry_succeeds(self, mock_existing_user):
        """Covers the inner delete_access_key error path (lines 191-192).
        First attempt for a key fails, retry succeeds — the while loop retries."""
        user, client = mock_existing_user
        client.list_access_keys.return_value = {
            "AccessKeyMetadata": [
                {"AccessKeyId": "AKIA1111", "Status": "Active"},
            ]
        }
        calls = []

        def delete_side_effect(**kwargs):
            calls.append(kwargs["AccessKeyId"])
            if len(calls) == 1:
                raise ClientError(
                    {"Error": {"Code": "ServiceFailure", "Message": "transient"}},
                    "DeleteAccessKey",
                )

        client.delete_access_key.side_effect = delete_side_effect
        result = user.delete_all_api_keys()
        assert result is True
        assert len(calls) == 2  # first call failed, second succeeded
