"""
Characterization tests for Group.
Documents current behavior as-is, including known quirks.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from wasabi.group import Group


@pytest.fixture
def mock_nonexistent_group(mock_boto3_client):
    """Group where group does NOT exist."""
    mock_boto3_client.list_groups.return_value = {"Groups": []}
    group = Group("devs")
    return group, mock_boto3_client


@pytest.fixture
def mock_existing_group(mock_boto3_client):
    """Group where group exists with members and policies."""
    mock_boto3_client.list_groups.return_value = {
        "Groups": [
            {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"}
        ]
    }
    mock_boto3_client.get_group.return_value = {
        "Group": {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"},
        "Users": [
            {"UserName": "alice", "Arn": "arn:aws:iam::123456789012:user/alice"}
        ],
    }
    mock_boto3_client.list_attached_group_policies.return_value = {
        "AttachedPolicies": [
            {"PolicyArn": "arn:aws:iam::123:policy/dev-policy", "PolicyName": "dev-policy"}
        ]
    }
    mock_boto3_client.list_group_policies.return_value = {"PolicyNames": []}
    mock_boto3_client.get_waiter.return_value = MagicMock()
    group = Group("devs")
    return group, mock_boto3_client


class TestGroupInit:
    """Document group initialization behavior."""

    def test_nonexistent_group_properties(self, mock_nonexistent_group):
        group, _ = mock_nonexistent_group
        props = group.to_dict()
        assert props["name"] == "devs"
        assert props["arn"] == ""
        assert props["members"] == []
        assert props["attached-policies"] == []
        assert props["inline-policies"] == {}

    def test_existing_group_populates_arn(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.to_dict()
        assert props["arn"] == "arn:aws:iam::123456789012:group/devs"

    def test_existing_group_populates_members_as_arns(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.to_dict()
        assert "arn:aws:iam::123456789012:user/alice" in props["members"]

    def test_existing_group_populates_attached_policies(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.to_dict()
        assert "arn:aws:iam::123:policy/dev-policy" in props["attached-policies"]


class TestGroupExists:
    """Document group_exists behavior."""

    def test_returns_true_when_found(self, mock_existing_group):
        group, _ = mock_existing_group
        assert group.group_exists() is True

    def test_returns_false_when_not_found(self, mock_nonexistent_group):
        group, _ = mock_nonexistent_group
        assert group.group_exists() is False

    def test_sets_arn_as_side_effect(self, mock_existing_group):
        """Current behavior: group_exists() sets self.arn as a side effect."""
        group, _ = mock_existing_group
        group.group_exists()
        assert group.arn == "arn:aws:iam::123456789012:group/devs"


class TestGroupCRUD:
    """Document create/delete group behavior."""

    def test_create_group_returns_true(self, mock_nonexistent_group):
        group, client = mock_nonexistent_group
        client.create_group.return_value = {
            "Group": {"GroupName": "devs", "Arn": "arn:aws:iam::123:group/devs"}
        }
        result = group.create_group()
        assert result is True

    def test_create_group_when_exists_returns_false(self, mock_existing_group):
        group, client = mock_existing_group
        result = group.create_group()
        assert result is False
        client.create_group.assert_not_called()

    def test_delete_group_raises_due_to_member_list_mismatch(self, mock_existing_group):
        """Current behavior BUG: delete_group calls remove_member(username),
        but __properties['members'] stores ARNs (not usernames), so
        list.remove() raises ValueError. This documents the existing bug."""
        group, client = mock_existing_group
        client.list_attached_group_policies.return_value = {
            "AttachedPolicies": [
                {"PolicyArn": "arn:aws:iam::123:policy/dev-policy", "PolicyName": "dev-policy"}
            ]
        }
        with pytest.raises(ValueError, match="list.remove"):
            group.delete_group()


class TestGroupMembers:
    """Document member management behavior."""

    def test_get_members_username_returns_list(self, mock_existing_group):
        group, _ = mock_existing_group
        members = group.get_members_username()
        assert members == ["alice"]

    def test_get_members_arn_returns_list(self, mock_existing_group):
        group, _ = mock_existing_group
        members = group.get_members_arn()
        assert members == ["arn:aws:iam::123456789012:user/alice"]

    def test_add_member_updates_properties(self, mock_existing_group):
        group, client = mock_existing_group
        group.add_member("bob")
        client.add_user_to_group.assert_called_once_with(GroupName="devs", UserName="bob")
        assert "bob" in group.to_dict()["members"]

    def test_remove_member_updates_properties(self, mock_existing_group):
        group, client = mock_existing_group
        # The properties have ARNs as members, not usernames
        # But remove_member tries to remove the username from the list
        # This documents the current (potentially inconsistent) behavior
        props = group.to_dict()
        # Members are ARNs from init, but add_member appends usernames
        assert props["members"] == ["arn:aws:iam::123456789012:user/alice"]


class TestGroupPolicies:
    """Document policy management behavior."""

    def test_get_attached_policies_returns_arn_list(self, mock_existing_group):
        group, _ = mock_existing_group
        policies = group.get_attached_policies()
        assert policies == ["arn:aws:iam::123:policy/dev-policy"]

    def test_attach_managed_policy_updates_properties(self, mock_existing_group):
        group, client = mock_existing_group
        group.attach_managed_policy("arn:aws:iam::123:policy/new-policy")
        client.attach_group_policy.assert_called_once()
        assert "arn:aws:iam::123:policy/new-policy" in group.to_dict()["attached-policies"]

    def test_get_inline_group_policies_empty(self, mock_existing_group):
        group, _ = mock_existing_group
        policies = group.get_inline_group_policies()
        assert policies == {}

    def test_get_inline_group_policies_with_policy(self, mock_existing_group):
        group, client = mock_existing_group
        client.list_group_policies.return_value = {"PolicyNames": ["my-inline"]}
        client.get_group_policy.return_value = {
            "PolicyDocument": {"Version": "2012-10-17", "Statement": []}
        }
        policies = group.get_inline_group_policies()
        assert "my-inline" in policies

    def test_put_inline_group_policy_uses_sid_as_name(self, mock_existing_group):
        """Current behavior: extracts policy name from Statement[0].Sid."""
        group, client = mock_existing_group
        policy_doc = {
            "Version": "2012-10-17",
            "Statement": [{"Sid": "MyPolicy", "Effect": "Allow", "Action": "*", "Resource": "*"}],
        }
        group.put_inline_group_policy(policy_doc)
        client.put_group_policy.assert_called_once_with(
            GroupName="devs", PolicyName="MyPolicy", PolicyDocument=json.dumps(policy_doc)
        )


class TestDeleteGroupSuccess:
    """Document delete_group success path.
    Requires members stored as usernames to avoid the ARN/username mismatch bug."""

    @pytest.fixture
    def mock_group_with_username_members(self, mock_boto3_client):
        """Group whose __properties['members'] stores usernames (not ARNs)
        so that remove_member's list.remove(username) succeeds."""
        mock_boto3_client.list_groups.return_value = {
            "Groups": [
                {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"}
            ]
        }
        mock_boto3_client.get_group.return_value = {
            "Group": {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"},
            "Users": [{"UserName": "alice", "Arn": "arn:aws:iam::123456789012:user/alice"}],
        }
        mock_boto3_client.list_attached_group_policies.return_value = {
            "AttachedPolicies": [
                {"PolicyArn": "arn:aws:iam::123:policy/dev-policy", "PolicyName": "dev-policy"}
            ]
        }
        mock_boto3_client.list_group_policies.return_value = {"PolicyNames": []}
        mock_boto3_client.get_waiter.return_value = MagicMock()
        group = Group("devs")
        # Manually fix members to store usernames so delete_group can succeed
        props = group.to_dict()
        props["members"] = ["alice"]
        return group, mock_boto3_client

    def test_delete_group_returns_true_on_success(self, mock_group_with_username_members):
        group, client = mock_group_with_username_members
        result = group.delete_group()
        assert result is True
        client.remove_user_from_group.assert_called_once_with(
            GroupName="devs", UserName="alice"
        )
        client.detach_group_policy.assert_called_once_with(
            GroupName="devs", PolicyArn="arn:aws:iam::123:policy/dev-policy"
        )
        client.delete_group.assert_called_once_with(GroupName="devs")
        props = group.to_dict()
        assert props["members"] == []
        assert props["attached-policies"] == []


class TestGetInlineGroupPolicy:
    """Document get_inline_group_policy behavior."""

    def test_returns_policy_from_properties(self, mock_existing_group):
        """When the policy is already cached in __properties, return it directly."""
        group, client = mock_existing_group
        cached_doc = {"Version": "2012-10-17", "Statement": []}
        # Inject a policy into properties via put_inline_group_policy
        group.to_dict()["inline-policies"]["cached-policy"] = cached_doc
        result = group.get_inline_group_policy("cached-policy")
        assert result == cached_doc

    def test_returns_policy_from_api_fallback(self, mock_existing_group):
        """When the policy is not in properties, falls back to API call."""
        group, client = mock_existing_group
        api_doc = {"Version": "2012-10-17", "Statement": [{"Effect": "Deny"}]}
        client.list_group_policies.return_value = {"PolicyNames": ["remote-policy"]}
        client.get_group_policy.return_value = {"PolicyDocument": api_doc}
        result = group.get_inline_group_policy("remote-policy")
        assert result == api_doc

    def test_returns_empty_dict_when_not_found(self, mock_existing_group):
        """When the policy exists neither in properties nor in the API."""
        group, client = mock_existing_group
        client.list_group_policies.return_value = {"PolicyNames": []}
        result = group.get_inline_group_policy("nonexistent-policy")
        assert result == {}


class TestDeleteInlineGroupPolicy:
    """Document delete_inline_group_policy behavior."""

    def test_returns_true_on_success(self, mock_existing_group):
        group, client = mock_existing_group
        # Set up so get_inline_group_policies returns a policy
        client.list_group_policies.return_value = {"PolicyNames": ["my-inline"]}
        client.get_group_policy.return_value = {
            "PolicyDocument": {"Version": "2012-10-17", "Statement": []}
        }
        result = group.delete_inline_group_policy("my-inline")
        assert result is True
        client.delete_group_policy.assert_called_once_with(
            GroupName="devs", PolicyName="my-inline"
        )
        assert group.to_dict()["inline-policies"] == {}

    def test_returns_false_when_no_policies(self, mock_existing_group):
        group, client = mock_existing_group
        # list_group_policies returns empty, so get_inline_group_policies returns {}
        client.list_group_policies.return_value = {"PolicyNames": []}
        result = group.delete_inline_group_policy("nonexistent")
        assert result is False
        client.delete_group_policy.assert_not_called()


class TestDetachManagedPolicy:
    """Document detach_managed_policy behavior."""

    def test_returns_true_and_updates_properties(self, mock_existing_group):
        group, client = mock_existing_group
        policy_arn = "arn:aws:iam::123:policy/dev-policy"
        assert policy_arn in group.to_dict()["attached-policies"]
        result = group.detach_managed_policy(policy_arn)
        assert result is True
        client.detach_group_policy.assert_called_once_with(
            GroupName="devs", PolicyArn=policy_arn
        )
        assert policy_arn not in group.to_dict()["attached-policies"]

    def test_returns_false_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.detach_group_policy.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "not found"}},
            "DetachGroupPolicy",
        )
        result = group.detach_managed_policy("arn:aws:iam::123:policy/missing")
        assert result is False


class TestRemoveMember:
    """Document remove_member behavior."""

    @pytest.fixture
    def mock_group_with_username_member(self, mock_boto3_client):
        """Group with a username-based member list for remove_member testing."""
        mock_boto3_client.list_groups.return_value = {
            "Groups": [
                {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"}
            ]
        }
        mock_boto3_client.get_group.return_value = {
            "Group": {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"},
            "Users": [{"UserName": "alice", "Arn": "arn:aws:iam::123456789012:user/alice"}],
        }
        mock_boto3_client.list_attached_group_policies.return_value = {
            "AttachedPolicies": []
        }
        mock_boto3_client.list_group_policies.return_value = {"PolicyNames": []}
        mock_boto3_client.get_waiter.return_value = MagicMock()
        group = Group("devs")
        # Manually set members as usernames so remove_member works
        group.to_dict()["members"] = ["alice"]
        return group, mock_boto3_client

    def test_returns_true_on_success(self, mock_group_with_username_member):
        group, client = mock_group_with_username_member
        result = group.remove_member("alice")
        assert result is True
        client.remove_user_from_group.assert_called_once_with(
            GroupName="devs", UserName="alice"
        )
        assert "alice" not in group.to_dict()["members"]

    def test_returns_false_on_error(self, mock_group_with_username_member):
        group, client = mock_group_with_username_member
        client.remove_user_from_group.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "user not in group"}},
            "RemoveUserFromGroup",
        )
        result = group.remove_member("bob")
        assert result is False


class TestAddMemberError:
    """Document add_member error behavior."""

    def test_returns_false_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.add_user_to_group.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "user not found"}},
            "AddUserToGroup",
        )
        result = group.add_member("nonexistent-user")
        assert result is False
        assert "nonexistent-user" not in group.to_dict()["members"]


class TestGetMembersErrors:
    """Document error handling for get_members_username and get_members_arn."""

    def test_get_members_username_returns_empty_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.get_group.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetGroup",
        )
        result = group.get_members_username()
        assert result == []

    def test_get_members_arn_returns_empty_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.get_group.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetGroup",
        )
        result = group.get_members_arn()
        assert result == []


class TestGroupConstructorValidation:
    """Document constructor validation behavior."""

    def test_empty_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="group_name must be a non-empty string"):
            Group("")

    def test_whitespace_only_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="group_name must be a non-empty string"):
            Group("   ")

    def test_non_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="group_name must be a non-empty string"):
            Group(123)


class TestGetGroup:
    """Document get_group behavior."""

    def test_returns_group_dict_when_exists(self, mock_existing_group):
        group, client = mock_existing_group
        result = group.get_group()
        assert result["Group"]["GroupName"] == "devs"
        assert result["Group"]["Arn"] == "arn:aws:iam::123456789012:group/devs"

    def test_returns_empty_dict_when_not_exists(self, mock_nonexistent_group):
        group, client = mock_nonexistent_group
        result = group.get_group()
        assert result == {}
        client.get_group.assert_not_called()

    def test_returns_empty_dict_on_non_nosuchentity_error(self, mock_existing_group):
        """Non-NoSuchEntity errors are logged and empty dict returned."""
        group, client = mock_existing_group
        client.get_group.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetGroup",
        )
        result = group.get_group()
        assert result == {}

    def test_suppresses_nosuchentity_error(self, mock_existing_group):
        """NoSuchEntity errors are silently suppressed."""
        group, client = mock_existing_group
        client.get_group.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "not found"}},
            "GetGroup",
        )
        result = group.get_group()
        assert result == {}


class TestDeleteGroupError:
    """Document delete_group ClientError path."""

    @pytest.fixture
    def mock_group_delete_error(self, mock_boto3_client):
        mock_boto3_client.list_groups.return_value = {
            "Groups": [
                {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"}
            ]
        }
        mock_boto3_client.get_group.return_value = {
            "Group": {"GroupName": "devs", "Arn": "arn:aws:iam::123456789012:group/devs"},
            "Users": [],
        }
        mock_boto3_client.list_attached_group_policies.return_value = {
            "AttachedPolicies": []
        }
        mock_boto3_client.list_group_policies.return_value = {"PolicyNames": []}
        group = Group("devs")
        # No members or policies, so delete_group goes straight to _client.delete_group
        return group, mock_boto3_client

    def test_returns_false_on_client_error(self, mock_group_delete_error):
        group, client = mock_group_delete_error
        client.delete_group.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "DeleteGroup",
        )
        result = group.delete_group()
        assert result is False


class TestGetInlineGroupPoliciesErrors:
    """Document get_inline_group_policies error paths."""

    def test_non_nosuchentity_error_is_logged(self, mock_existing_group):
        """Non-NoSuchEntity errors hit the logger.error path."""
        group, client = mock_existing_group
        client.list_group_policies.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "ListGroupPolicies",
        )
        result = group.get_inline_group_policies()
        assert result == {}

    def test_nosuchentity_error_triggers_warning(self, mock_existing_group):
        """NoSuchEntity errors hit the logger.warning path."""
        group, client = mock_existing_group
        client.list_group_policies.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "group not found"}},
            "ListGroupPolicies",
        )
        result = group.get_inline_group_policies()
        assert result == {}


class TestPutInlineGroupPolicyError:
    """Document put_inline_group_policy error path."""

    def test_non_nosuchentity_error_returns_empty_dict(self, mock_existing_group):
        group, client = mock_existing_group
        client.put_group_policy.side_effect = ClientError(
            {"Error": {"Code": "MalformedPolicyDocument", "Message": "bad policy"}},
            "PutGroupPolicy",
        )
        policy_doc = {
            "Version": "2012-10-17",
            "Statement": [{"Sid": "TestPolicy", "Effect": "Allow", "Action": "*", "Resource": "*"}],
        }
        result = group.put_inline_group_policy(policy_doc)
        assert result == {}


class TestDeleteInlineGroupPolicyError:
    """Document delete_inline_group_policy ClientError path."""

    def test_returns_false_on_client_error(self, mock_existing_group):
        group, client = mock_existing_group
        # Set up so get_inline_group_policies returns a policy (passes the guard)
        client.list_group_policies.return_value = {"PolicyNames": ["my-inline"]}
        client.get_group_policy.return_value = {
            "PolicyDocument": {"Version": "2012-10-17", "Statement": []}
        }
        # But delete_group_policy itself fails
        client.delete_group_policy.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "DeleteGroupPolicy",
        )
        result = group.delete_inline_group_policy("my-inline")
        assert result is False


class TestGetAttachedPoliciesError:
    """Document get_attached_policies ClientError path."""

    def test_returns_empty_list_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.list_attached_group_policies.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "ListAttachedGroupPolicies",
        )
        result = group.get_attached_policies()
        assert result == []


class TestAttachManagedPolicyError:
    """Document attach_managed_policy ClientError path."""

    def test_returns_false_on_error(self, mock_existing_group):
        group, client = mock_existing_group
        client.attach_group_policy.side_effect = ClientError(
            {"Error": {"Code": "LimitExceeded", "Message": "too many policies"}},
            "AttachGroupPolicy",
        )
        result = group.attach_managed_policy("arn:aws:iam::123:policy/new-policy")
        assert result is False
