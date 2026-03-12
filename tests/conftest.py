"""
Shared fixtures for wasabi characterization tests.
These mock external dependencies (boto3, requests) so tests
never hit real APIs.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def set_credentials(monkeypatch):
    """Ensure credentials env vars are always set for tests."""
    monkeypatch.setenv("WASABI_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("WASABI_SECRET_KEY", "test-secret-key")


@pytest.fixture
def mock_boto3_client():
    """Returns a factory that patches boto3.client and returns the mock client."""
    with patch("boto3.client") as mock_client_ctor:
        client = MagicMock()
        mock_client_ctor.return_value = client
        yield client


@pytest.fixture
def mock_iam_client(mock_boto3_client):
    """A boto3 mock pre-configured as an IAM client."""
    return mock_boto3_client


@pytest.fixture
def mock_s3_client(mock_boto3_client):
    """A boto3 mock pre-configured as an S3 client."""
    return mock_boto3_client


@pytest.fixture
def mock_sts_client(mock_boto3_client):
    """A boto3 mock pre-configured as an STS client."""
    mock_boto3_client.get_caller_identity.return_value = {
        "Account": "123456789012"
    }
    return mock_boto3_client
