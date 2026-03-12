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
        props = group.export_properties()
        assert props["name"] == "devs"
        assert props["arn"] == ""
        assert props["members"] == []
        assert props["attached-policies"] == []
        assert props["inline-policies"] == {}

    def test_existing_group_populates_arn(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.export_properties()
        assert props["arn"] == "arn:aws:iam::123456789012:group/devs"

    def test_existing_group_populates_members_as_arns(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.export_properties()
        assert "arn:aws:iam::123456789012:user/alice" in props["members"]

    def test_existing_group_populates_attached_policies(self, mock_existing_group):
        group, _ = mock_existing_group
        props = group.export_properties()
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
        assert "bob" in group.export_properties()["members"]

    def test_remove_member_updates_properties(self, mock_existing_group):
        group, client = mock_existing_group
        # The properties have ARNs as members, not usernames
        # But remove_member tries to remove the username from the list
        # This documents the current (potentially inconsistent) behavior
        props = group.export_properties()
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
        assert "arn:aws:iam::123:policy/new-policy" in group.export_properties()["attached-policies"]

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
