"""
Characterization tests for Policy.
Documents current behavior as-is, including known quirks.
"""
import json
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

from wasabi.policy import Policy


@pytest.fixture
def mock_nonexistent_policy(mock_boto3_client):
    """Policy where policy does NOT exist."""
    mock_boto3_client.get_caller_identity.return_value = {"Account": "123456789012"}
    mock_boto3_client.get_policy.side_effect = ClientError(
        {"Error": {"Code": "NoSuchEntity", "Message": "not found"}}, "GetPolicy"
    )
    policy = Policy("test-policy")
    return policy, mock_boto3_client


@pytest.fixture
def mock_existing_policy(mock_boto3_client):
    """Policy where policy exists."""
    mock_boto3_client.get_caller_identity.return_value = {"Account": "123456789012"}
    mock_boto3_client.get_policy.return_value = {
        "Policy": {
            "PolicyName": "test-policy",
            "Arn": "arn:aws:iam::123456789012:policy/test-policy",
            "DefaultVersionId": "v1",
        }
    }
    mock_boto3_client.get_policy_version.return_value = {
        "PolicyVersion": {
            "Document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "test-policy",
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject"],
                        "Resource": ["arn:aws:s3:::my-bucket/*"],
                    }
                ],
            },
            "IsDefaultVersion": True,
        }
    }
    policy = Policy("test-policy")
    return policy, mock_boto3_client


class TestPolicyInit:
    """Document policy initialization behavior."""

    def test_nonexistent_policy_has_default_document(self, mock_nonexistent_policy):
        policy, _ = mock_nonexistent_policy
        props = policy.export_properties()
        assert props["name"] == "test-policy"
        assert props["arn"] == "arn:aws:iam::123456789012:policy/test-policy"
        doc = props["document"]
        assert doc["Version"] == "2012-10-17"
        assert doc["Statement"][0]["Sid"] == "test-policy"
        assert doc["Statement"][0]["Action"] == []
        assert doc["Statement"][0]["Resource"] == []

    def test_existing_policy_populates_all_properties(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        props = policy.export_properties()
        assert props["name"] == "test-policy"
        assert props["version"] == "v1"
        assert props["is-default-version"] is True
        assert props["actions"] == ["s3:GetObject", "s3:PutObject"]
        assert props["resources"] == ["arn:aws:s3:::my-bucket/*"]

    def test_arn_derived_from_sts_account_id(self, mock_nonexistent_policy):
        """Current behavior: makes STS call during __init__ to build ARN."""
        policy, _ = mock_nonexistent_policy
        assert policy.export_properties()["arn"] == "arn:aws:iam::123456789012:policy/test-policy"


class TestPolicyExists:
    """Document policy_exists behavior."""

    def test_returns_true_when_found(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        assert policy.policy_exists() is True

    def test_returns_false_when_not_found(self, mock_nonexistent_policy):
        policy, _ = mock_nonexistent_policy
        assert policy.policy_exists() is False


class TestPolicyCRUD:
    """Document create/update/delete policy behavior."""

    def test_create_policy_calls_api(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        doc = {"Version": "2012-10-17", "Statement": []}
        client.create_policy.return_value = {
            "Policy": {"Arn": "arn:aws:iam::123456789012:policy/test-policy"}
        }
        result = policy.create_policy(doc)
        client.create_policy.assert_called_once_with(
            PolicyName="test-policy", PolicyDocument=json.dumps(doc)
        )
        assert "Policy" in result

    def test_create_policy_when_exists_returns_existing(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        client.create_policy.side_effect = ClientError(
            {"Error": {"Code": "EntityAlreadyExists", "Message": "exists"}}, "CreatePolicy"
        )
        # get_policy needs to work for fallback
        client.get_policy.side_effect = None
        client.get_policy.return_value = {
            "Policy": {"PolicyName": "test-policy", "Arn": "arn:..."}
        }
        result = policy.create_policy({})
        assert result["PolicyName"] == "test-policy"

    def test_update_policy_creates_new_version(self, mock_existing_policy):
        policy, client = mock_existing_policy
        doc = {"Version": "2012-10-17", "Statement": []}
        policy.update_policy(doc)
        client.create_policy_version.assert_called_once_with(
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy",
            PolicyDocument=json.dumps(doc),
            SetAsDefault=True,
        )

    def test_delete_policy_when_exists(self, mock_existing_policy):
        policy, client = mock_existing_policy
        policy.delete_policy()
        client.delete_policy.assert_called_once_with(
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy"
        )

    def test_delete_policy_when_not_exists_is_noop(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        policy.delete_policy()
        client.delete_policy.assert_not_called()


class TestPolicyDocument:
    """Document policy document retrieval."""

    def test_get_policy_document_returns_document(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        doc = policy.get_policy_document()
        assert doc["Version"] == "2012-10-17"
        assert len(doc["Statement"]) == 1

    def test_get_policy_actions_returns_action_list(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        actions = policy.get_policy_actions()
        assert actions == ["s3:GetObject", "s3:PutObject"]

    def test_get_policy_resources_returns_resource_list(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        resources = policy.get_policy_resources()
        assert resources == ["arn:aws:s3:::my-bucket/*"]

    def test_get_policy_version_id(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        version = policy.get_policy_version_id()
        assert version == "v1"

    def test_is_default_version_returns_bool(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        assert policy.is_default_version() is True
