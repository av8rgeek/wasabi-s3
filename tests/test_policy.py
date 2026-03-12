"""
Characterization tests for Policy.
Documents current behavior as-is, including known quirks.
"""
import json

import pytest
from botocore.exceptions import ClientError

from wasabi_s3.policy import Policy


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
        props = policy.to_dict()
        assert props["name"] == "test-policy"
        assert props["arn"] == "arn:aws:iam::123456789012:policy/test-policy"
        doc = props["document"]
        assert doc["Version"] == "2012-10-17"
        assert doc["Statement"][0]["Sid"] == "test-policy"
        assert doc["Statement"][0]["Action"] == []
        assert doc["Statement"][0]["Resource"] == []

    def test_existing_policy_populates_all_properties(self, mock_existing_policy):
        policy, _ = mock_existing_policy
        props = policy.to_dict()
        assert props["name"] == "test-policy"
        assert props["version"] == "v1"
        assert props["is-default-version"] is True
        assert props["actions"] == ["s3:GetObject", "s3:PutObject"]
        assert props["resources"] == ["arn:aws:s3:::my-bucket/*"]

    def test_arn_derived_from_sts_account_id(self, mock_nonexistent_policy):
        """Current behavior: makes STS call during __init__ to build ARN."""
        policy, _ = mock_nonexistent_policy
        assert policy.to_dict()["arn"] == "arn:aws:iam::123456789012:policy/test-policy"


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


class TestListVersions:
    """Document list_versions behavior."""

    def test_returns_list_of_versions(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.list_policy_versions.return_value = {
            "Versions": [
                {"VersionId": "v1", "IsDefaultVersion": True},
                {"VersionId": "v2", "IsDefaultVersion": False},
            ]
        }
        versions = policy.list_versions()
        assert len(versions) == 2
        assert versions[0]["VersionId"] == "v1"
        assert versions[1]["VersionId"] == "v2"
        client.list_policy_versions.assert_called_once_with(
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy"
        )

    def test_returns_empty_list_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.list_policy_versions.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "not found"}},
            "ListPolicyVersions",
        )
        versions = policy.list_versions()
        assert versions == []


class TestDeleteVersion:
    """Document delete_version behavior."""

    def test_returns_true_on_success(self, mock_existing_policy):
        policy, client = mock_existing_policy
        result = policy.delete_version("v2")
        assert result is True
        client.delete_policy_version.assert_called_once_with(
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy",
            VersionId="v2",
        )

    def test_returns_false_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.delete_policy_version.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "version not found"}},
            "DeletePolicyVersion",
        )
        result = policy.delete_version("v99")
        assert result is False


class TestDetachFromAll:
    """Document detach_from_all behavior."""

    def test_returns_true_and_detaches_groups_and_users(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.list_entities_for_policy.return_value = {
            "PolicyGroups": [{"GroupName": "devs"}, {"GroupName": "admins"}],
            "PolicyUsers": [{"UserName": "alice"}],
        }
        result = policy.detach_from_all()
        assert result is True
        assert client.detach_group_policy.call_count == 2
        client.detach_group_policy.assert_any_call(
            GroupName="devs",
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy",
        )
        client.detach_group_policy.assert_any_call(
            GroupName="admins",
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy",
        )
        client.detach_user_policy.assert_called_once_with(
            UserName="alice",
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy",
        )

    def test_returns_true_with_no_attachments(self, mock_existing_policy):
        """When no groups or users are attached, still returns True."""
        policy, client = mock_existing_policy
        client.list_entities_for_policy.return_value = {
            "PolicyGroups": [],
            "PolicyUsers": [],
        }
        result = policy.detach_from_all()
        assert result is True
        client.detach_group_policy.assert_not_called()
        client.detach_user_policy.assert_not_called()

    def test_returns_false_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.list_entities_for_policy.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "policy not found"}},
            "ListEntitiesForPolicy",
        )
        result = policy.detach_from_all()
        assert result is False


class TestDeletePolicyReturnsBool:
    """Document delete_policy return value behavior."""

    def test_returns_true_on_success(self, mock_existing_policy):
        policy, client = mock_existing_policy
        result = policy.delete_policy()
        assert result is True
        client.delete_policy.assert_called_once_with(
            PolicyArn="arn:aws:iam::123456789012:policy/test-policy"
        )

    def test_returns_false_on_client_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.delete_policy.side_effect = ClientError(
            {"Error": {"Code": "DeleteConflict", "Message": "policy is attached"}},
            "DeletePolicy",
        )
        result = policy.delete_policy()
        assert result is False

    def test_returns_false_when_not_exists(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        result = policy.delete_policy()
        assert result is False
        client.delete_policy.assert_not_called()


class TestGetArnEmptyAccountId:
    """Document get_arn behavior when account_id is empty."""

    def test_returns_empty_string_when_account_id_empty(self, mock_boto3_client):
        """When get_account_id returns empty string, get_arn returns empty string."""
        mock_boto3_client.get_caller_identity.side_effect = ClientError(
            {"Error": {"Code": "ExpiredToken", "Message": "token expired"}},
            "GetCallerIdentity",
        )
        # get_policy will also fail since ARN is empty, but that's fine for this test
        mock_boto3_client.get_policy.side_effect = ClientError(
            {"Error": {"Code": "NoSuchEntity", "Message": "not found"}}, "GetPolicy"
        )
        policy = Policy("test-policy")
        assert policy.to_dict()["arn"] == ""


class TestPolicyConstructorValidation:
    """Document constructor validation behavior."""

    def test_empty_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="policy_name must be a non-empty string"):
            Policy("")

    def test_whitespace_only_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="policy_name must be a non-empty string"):
            Policy("   ")

    def test_non_string_raises_value_error(self, mock_boto3_client):
        with pytest.raises(ValueError, match="policy_name must be a non-empty string"):
            Policy(123)


class TestPolicyExistsNonNoSuchEntityError:
    """Document policy_exists behavior on unexpected errors."""

    def test_non_nosuchentity_error_is_logged(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        client.get_policy.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetPolicy",
        )
        result = policy.policy_exists()
        assert result is False


class TestCreatePolicyNonEntityExistsError:
    """Document create_policy behavior on non-EntityAlreadyExists errors."""

    def test_non_entity_exists_error_returns_empty_dict(self, mock_nonexistent_policy):
        policy, client = mock_nonexistent_policy
        client.create_policy.side_effect = ClientError(
            {"Error": {"Code": "MalformedPolicyDocument", "Message": "bad doc"}},
            "CreatePolicy",
        )
        result = policy.create_policy({"Version": "2012-10-17", "Statement": []})
        assert result == {}


class TestGetPolicyVersionIdError:
    """Document get_policy_version_id error path."""

    def test_returns_empty_string_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.get_policy.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetPolicy",
        )
        result = policy.get_policy_version_id()
        assert result == ""


class TestIsDefaultVersionError:
    """Document is_default_version error path."""

    def test_returns_false_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.get_policy_version.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetPolicyVersion",
        )
        result = policy.is_default_version()
        assert result is False


class TestGetPolicyError:
    """Document get_policy error path."""

    def test_returns_empty_dict_on_error(self, mock_existing_policy):
        policy, client = mock_existing_policy
        client.get_policy.side_effect = ClientError(
            {"Error": {"Code": "ServiceFailure", "Message": "internal error"}},
            "GetPolicy",
        )
        result = policy.get_policy()
        assert result == {}
