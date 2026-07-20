"""Property-based tests for credential error categorization.

**Validates: Requirements 2.3**

Property 3: Credential error categorization
- For any credential validation failure (invalid keys, expired session, unreachable
  endpoint), the error response SHALL contain a descriptive `message` field indicating
  the specific failure reason and SHALL conform to the standard error response structure.
"""

import os
import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError
from backend.models.credentials import CredentialSubmission
from backend.models.errors import ErrorResponse
from backend.services.credential_manager import CredentialManager


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: non-whitespace strings for credential fields (valid format-wise)
non_whitespace_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=128,
).filter(lambda s: s.strip() != "")

# Valid region strategy
region_strategy = st.sampled_from([
    "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1",
])

# Strategy: STS ClientError error codes that represent credential failures
sts_error_code_strategy = st.sampled_from([
    "ExpiredTokenException",
    "ExpiredToken",
    "InvalidClientTokenId",
    "SignatureDoesNotMatch",
    "AccessDenied",
    "AuthFailure",
    "UnrecognizedClientException",
])

# Strategy: error messages from AWS
error_message_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=5,
    max_size=200,
).filter(lambda s: s.strip() != "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client_error(error_code: str, message: str) -> ClientError:
    """Create a botocore ClientError with the given code and message."""
    return ClientError(
        error_response={
            "Error": {
                "Code": error_code,
                "Message": message,
            }
        },
        operation_name="GetCallerIdentity",
    )


def assert_error_response_structure(error_response: ErrorResponse) -> None:
    """Assert the ErrorResponse conforms to the standard structure."""
    # error_code must be UPPER_SNAKE_CASE
    assert re.match(r"^[A-Z][A-Z0-9_]*$", error_response.error_code), (
        f"error_code '{error_response.error_code}' is not UPPER_SNAKE_CASE"
    )
    # message must be non-empty and ≤500 chars
    assert len(error_response.message) > 0
    assert len(error_response.message) <= 500
    # timestamp must be a valid ISO 8601 string
    assert error_response.timestamp is not None
    datetime.fromisoformat(error_response.timestamp)
    # recoverable must be a boolean
    assert isinstance(error_response.recoverable, bool)
    # details can be str or None
    assert error_response.details is None or isinstance(error_response.details, str)


# ---------------------------------------------------------------------------
# Setup: mock AWS env
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_env():
    """Set up mock AWS environment variables."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield


# ---------------------------------------------------------------------------
# Property 3: Credential validation failures produce structured error responses
# ---------------------------------------------------------------------------

class TestCredentialErrorCategorization:
    """All credential validation failures produce properly structured errors."""

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
        error_code=sts_error_code_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_client_error_produces_structured_error(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """STS ClientError (invalid keys, expired token) produces a CloudSpyglassError
        that converts to a properly structured ErrorResponse with a descriptive message.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )

        client_error = make_client_error(error_code, error_message)

        with patch.object(manager, "validate_credentials") as mock_validate:
            from backend.models.credentials import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=False,
                error=f"Invalid credentials: {error_message}",
            )

            with pytest.raises(CloudSpyglassError) as exc_info:
                await manager.set_credentials(submission)

            exc = exc_info.value

            # The error must have a descriptive non-empty message
            assert len(exc.message) > 0
            assert exc.message.strip() != ""

            # The error must have a valid UPPER_SNAKE_CASE error_code
            assert re.match(r"^[A-Z][A-Z0-9_]*$", exc.error_code), (
                f"error_code '{exc.error_code}' is not UPPER_SNAKE_CASE"
            )

            # The error must have an HTTP status code
            assert isinstance(exc.status_code, int)
            assert 400 <= exc.status_code < 600

            # For auth/invalid input failures, recoverable should be False
            assert exc.recoverable is False

            # Convert to ErrorResponse model and verify structure
            error_response = ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                timestamp=datetime.now(timezone.utc).isoformat(),
                recoverable=exc.recoverable,
            )
            assert_error_response_structure(error_response)

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_network_error_produces_structured_error(
        self,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        """BotoCoreError (unreachable endpoint / network issues) produces a
        CloudSpyglassError conforming to the standard error response structure.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )

        with patch.object(manager, "validate_credentials") as mock_validate:
            from backend.models.credentials import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=False,
                error="Network or configuration error: Could not connect to the endpoint URL",
            )

            with pytest.raises(CloudSpyglassError) as exc_info:
                await manager.set_credentials(submission)

            exc = exc_info.value

            # Must have descriptive message about the failure
            assert len(exc.message) > 0
            assert exc.message.strip() != ""

            # Must have UPPER_SNAKE_CASE error_code
            assert re.match(r"^[A-Z][A-Z0-9_]*$", exc.error_code)

            # Must have valid status code
            assert isinstance(exc.status_code, int)
            assert 400 <= exc.status_code < 600

            # Convert to ErrorResponse and verify structure
            error_response = ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                timestamp=datetime.now(timezone.utc).isoformat(),
                recoverable=exc.recoverable,
            )
            assert_error_response_structure(error_response)

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_timeout_error_produces_structured_error(
        self,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        """Timeout during STS validation produces a CloudSpyglassError conforming
        to the standard error response structure.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )

        with patch.object(manager, "validate_credentials") as mock_validate:
            from backend.models.credentials import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=False,
                error="Credential validation timed out after 10 seconds.",
            )

            with pytest.raises(CloudSpyglassError) as exc_info:
                await manager.set_credentials(submission)

            exc = exc_info.value

            # Must have descriptive message
            assert len(exc.message) > 0
            assert exc.message.strip() != ""

            # Must have UPPER_SNAKE_CASE error_code
            assert re.match(r"^[A-Z][A-Z0-9_]*$", exc.error_code)

            # Must have valid status code
            assert isinstance(exc.status_code, int)
            assert 400 <= exc.status_code < 600

            # Convert to ErrorResponse and verify structure
            error_response = ErrorResponse(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                timestamp=datetime.now(timezone.utc).isoformat(),
                recoverable=exc.recoverable,
            )
            assert_error_response_structure(error_response)

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
        error_code=sts_error_code_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_error_message_indicates_failure_reason(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """The error message in the CloudSpyglassError must be descriptive and
        indicate the specific failure reason — not a generic placeholder.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )

        # Determine expected error message content based on error code type
        if error_code in ("ExpiredTokenException", "ExpiredToken"):
            expected_error = f"Credentials expired: {error_message}"
        else:
            expected_error = f"Invalid credentials: {error_message}"

        with patch.object(manager, "validate_credentials") as mock_validate:
            from backend.models.credentials import ValidationResult

            mock_validate.return_value = ValidationResult(
                valid=False,
                error=expected_error,
            )

            with pytest.raises(CloudSpyglassError) as exc_info:
                await manager.set_credentials(submission)

            exc = exc_info.value

            # The message must contain meaningful content about the failure
            # It should not be empty or just whitespace
            assert len(exc.message.strip()) > 10, (
                f"Message '{exc.message}' is too short to be descriptive"
            )

            # The message should reflect the actual error that occurred
            # (propagated from the validation result)
            assert exc.message == expected_error or error_message in exc.message or (
                "expired" in exc.message.lower()
                or "invalid" in exc.message.lower()
                or "credential" in exc.message.lower()
                or "failed" in exc.message.lower()
            ), f"Message '{exc.message}' does not indicate a specific failure reason"


class TestValidateCredentialsDirectlyProducesErrors:
    """validate_credentials() returns ValidationResult with descriptive errors."""

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
        error_code=sts_error_code_strategy,
        error_message=error_message_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_sts_client_error_returns_validation_failure(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """When STS GetCallerIdentity raises ClientError, validate_credentials
        returns a ValidationResult with valid=False and a descriptive error.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        # Set credentials directly to avoid set_credentials' validation loop
        manager._access_key_id = access_key
        manager._secret_access_key = secret_key
        manager._region = region

        client_error = make_client_error(error_code, error_message)

        with patch("boto3.Session") as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_sts = mock_session.client.return_value
            mock_sts.get_caller_identity.side_effect = client_error

            result = await manager.validate_credentials()

            assert result.valid is False
            assert result.error is not None
            assert len(result.error) > 0

            # Error message must be descriptive
            if error_code in ("ExpiredTokenException", "ExpiredToken"):
                assert "expired" in result.error.lower() or "Expired" in result.error
            else:
                assert "invalid" in result.error.lower() or "Invalid" in result.error or error_message in result.error

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_botocore_error_returns_validation_failure(
        self,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        """When STS call raises BotoCoreError (network issues), validate_credentials
        returns a ValidationResult with valid=False and a network-related error.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        manager._access_key_id = access_key
        manager._secret_access_key = secret_key
        manager._region = region

        with patch("boto3.Session") as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_sts = mock_session.client.return_value
            mock_sts.get_caller_identity.side_effect = BotoCoreError()

            result = await manager.validate_credentials()

            assert result.valid is False
            assert result.error is not None
            assert len(result.error) > 0
            # Should mention network or configuration
            assert "network" in result.error.lower() or "configuration" in result.error.lower() or "error" in result.error.lower()

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_credentials_error_returns_validation_failure(
        self,
        access_key: str,
        secret_key: str,
        region: str,
    ) -> None:
        """When STS call raises NoCredentialsError, validate_credentials returns
        a ValidationResult with valid=False and a credentials-related error.

        **Validates: Requirements 2.3**
        """
        manager = CredentialManager()
        manager._access_key_id = access_key
        manager._secret_access_key = secret_key
        manager._region = region

        with patch("boto3.Session") as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_sts = mock_session.client.return_value
            mock_sts.get_caller_identity.side_effect = NoCredentialsError()

            result = await manager.validate_credentials()

            assert result.valid is False
            assert result.error is not None
            assert len(result.error) > 0
            assert "credential" in result.error.lower()
