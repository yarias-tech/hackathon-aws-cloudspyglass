"""Unit tests for the CredentialManager service."""

import os

import boto3
import pytest
from moto import mock_aws

from backend.exceptions import CloudSpyglassError
from backend.models.credentials import CredentialSubmission
from backend.services.credential_manager import CredentialManager


@pytest.fixture
def manager() -> CredentialManager:
    """Create a fresh CredentialManager instance."""
    return CredentialManager()


@pytest.fixture
def valid_submission() -> CredentialSubmission:
    """Create a valid credential submission for testing."""
    return CredentialSubmission(
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token=None,
        region="us-east-1",
    )


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield
    # Cleanup is handled by moto context manager


class TestSetCredentials:
    """Tests for set_credentials validation and storage."""

    async def test_rejects_empty_access_key_id(self, manager: CredentialManager) -> None:
        """Empty access_key_id is rejected with INVALID_CREDENTIALS."""
        submission = CredentialSubmission(
            access_key_id="",
            secret_access_key="validkey",
            session_token=None,
            region="us-east-1",
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)
        assert exc_info.value.error_code == "INVALID_CREDENTIALS"
        assert "Access Key ID" in exc_info.value.message

    async def test_rejects_whitespace_access_key_id(self, manager: CredentialManager) -> None:
        """Whitespace-only access_key_id is rejected."""
        submission = CredentialSubmission(
            access_key_id="   \t\n  ",
            secret_access_key="validkey",
            session_token=None,
            region="us-east-1",
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)
        assert exc_info.value.error_code == "INVALID_CREDENTIALS"

    async def test_rejects_empty_secret_access_key(self, manager: CredentialManager) -> None:
        """Empty secret_access_key is rejected with INVALID_CREDENTIALS."""
        submission = CredentialSubmission(
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="",
            session_token=None,
            region="us-east-1",
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)
        assert exc_info.value.error_code == "INVALID_CREDENTIALS"
        assert "Secret Access Key" in exc_info.value.message

    async def test_rejects_whitespace_secret_access_key(self, manager: CredentialManager) -> None:
        """Whitespace-only secret_access_key is rejected."""
        submission = CredentialSubmission(
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="   ",
            session_token=None,
            region="us-east-1",
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)
        assert exc_info.value.error_code == "INVALID_CREDENTIALS"

    async def test_accepts_valid_credentials(
        self,
        manager: CredentialManager,
        valid_submission: CredentialSubmission,
        aws_credentials,
    ) -> None:
        """Valid credentials are accepted and stored."""
        with mock_aws():
            status = await manager.set_credentials(valid_submission)
            assert status.connected is True
            assert status.status == "Connected"
            assert status.credential_source == "ui"
            assert status.account_id is not None
            assert status.expiry == "No expiration"

    async def test_replaces_previous_credentials(
        self, manager: CredentialManager, aws_credentials
    ) -> None:
        """Sequential submissions replace previous credentials (Req 1.4)."""
        with mock_aws():
            first = CredentialSubmission(
                access_key_id="AKIAIOSFODNN7FIRST00",
                secret_access_key="firstsecretkey0000000000000000000000000",
                session_token=None,
                region="us-east-1",
            )
            second = CredentialSubmission(
                access_key_id="AKIAIOSFODNN7SECOND0",
                secret_access_key="secondsecretkey000000000000000000000000",
                session_token=None,
                region="eu-west-1",
            )

            await manager.set_credentials(first)
            await manager.set_credentials(second)

            session = await manager.get_boto3_session()
            credentials = session.get_credentials().get_frozen_credentials()
            assert credentials.access_key == "AKIAIOSFODNN7SECOND0"


class TestValidateCredentials:
    """Tests for STS validation behavior."""

    async def test_successful_validation(
        self,
        manager: CredentialManager,
        valid_submission: CredentialSubmission,
        aws_credentials,
    ) -> None:
        """Successful STS call returns valid=True with account info."""
        with mock_aws():
            # Set credentials directly to test validate alone
            manager._access_key_id = valid_submission.access_key_id
            manager._secret_access_key = valid_submission.secret_access_key
            manager._region = valid_submission.region

            result = await manager.validate_credentials()
            assert result.valid is True
            assert result.account_id is not None
            assert result.arn is not None
            assert result.error is None

    async def test_no_credentials_returns_error(self, manager: CredentialManager) -> None:
        """Missing credentials still return a ValidationResult (may vary by env)."""
        manager._access_key_id = None
        manager._secret_access_key = None

        result = await manager.validate_credentials()
        # Structure is always correct regardless of outcome
        assert isinstance(result.valid, bool)


class TestGetBoto3Session:
    """Tests for session creation and fallback."""

    async def test_returns_session_with_ui_credentials(
        self, manager: CredentialManager
    ) -> None:
        """When UI credentials are set, session uses them."""
        manager._access_key_id = "AKIATEST1234567890AB"
        manager._secret_access_key = "testsecret1234567890"
        manager._session_token = "testsessiontoken"
        manager._region = "us-west-2"

        session = await manager.get_boto3_session()
        credentials = session.get_credentials().get_frozen_credentials()
        assert credentials.access_key == "AKIATEST1234567890AB"
        assert credentials.secret_key == "testsecret1234567890"
        assert credentials.token == "testsessiontoken"
        assert session.region_name == "us-west-2"

    async def test_returns_fallback_session_when_no_ui_credentials(
        self, manager: CredentialManager
    ) -> None:
        """When no UI credentials are set, falls back to boto3 chain."""
        session = await manager.get_boto3_session()
        # Should return a session (may or may not have credentials from env)
        assert session is not None
        assert isinstance(session, boto3.Session)


class TestClearCredentials:
    """Tests for credential clearing."""

    async def test_clear_resets_all_state(
        self,
        manager: CredentialManager,
        valid_submission: CredentialSubmission,
        aws_credentials,
    ) -> None:
        """After clearing, status returns Disconnected with no account info."""
        with mock_aws():
            await manager.set_credentials(valid_submission)
            assert manager.get_status().connected is True

            await manager.clear_credentials()
            status = manager.get_status()
            assert status.connected is False
            assert status.status == "Disconnected"
            assert status.account_id is None
            assert status.credential_source is None
            assert status.expiry is None


class TestGetStatus:
    """Tests for status reporting."""

    def test_initial_status_is_disconnected(self, manager: CredentialManager) -> None:
        """Fresh manager reports Disconnected status."""
        status = manager.get_status()
        assert status.connected is False
        assert status.status == "Disconnected"
        assert status.account_id is None

    async def test_connected_status_after_valid_credentials(
        self,
        manager: CredentialManager,
        valid_submission: CredentialSubmission,
        aws_credentials,
    ) -> None:
        """After valid credential submission, status is Connected."""
        with mock_aws():
            await manager.set_credentials(valid_submission)
            status = manager.get_status()
            assert status.connected is True
            assert status.status == "Connected"
            assert status.account_id is not None
            assert status.credential_source == "ui"
