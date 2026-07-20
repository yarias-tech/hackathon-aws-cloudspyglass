"""Property-based tests for credential submission validation.

**Validates: Requirements 1.2, 1.6**

Property 1: Credential submission validation
- For any credential payload, if the access_key_id or secret_access_key field
  is empty or composed entirely of whitespace characters, the system SHALL reject
  the submission and return an error.
- Otherwise, if both fields contain at least one non-whitespace character, the
  system SHALL accept and store the credentials.
"""

import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from backend.exceptions import CloudSpyglassError
from backend.models.credentials import CredentialSubmission
from backend.services.credential_manager import CredentialManager


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Whitespace characters commonly encountered
WHITESPACE_CHARS = " \t\n\r\x0b\x0c"

# Strategy: strings that are empty or composed entirely of whitespace
whitespace_only_strategy = st.one_of(
    st.just(""),
    st.text(alphabet=WHITESPACE_CHARS, min_size=1, max_size=128),
)

# Strategy: strings with at least one non-whitespace character (max 128 to match model)
non_whitespace_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=128,
).filter(lambda s: s.strip() != "")

# Valid region strategy
region_strategy = st.sampled_from([
    "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1",
])


# ---------------------------------------------------------------------------
# Setup: mock AWS env for moto
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_env():
    """Set up mock AWS environment variables for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield


# ---------------------------------------------------------------------------
# Property: Invalid credentials are always rejected
# ---------------------------------------------------------------------------

class TestInvalidCredentialsRejected:
    """Empty or whitespace-only access_key_id/secret_access_key are rejected."""

    @given(
        access_key=whitespace_only_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50)
    async def test_whitespace_access_key_rejected(
        self, access_key: str, secret_key: str, region: str
    ) -> None:
        """Any whitespace-only access_key_id is rejected with INVALID_CREDENTIALS."""
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)

        assert exc_info.value.error_code == "INVALID_CREDENTIALS"
        assert exc_info.value.status_code == 400

    @given(
        access_key=non_whitespace_strategy,
        secret_key=whitespace_only_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50)
    async def test_whitespace_secret_key_rejected(
        self, access_key: str, secret_key: str, region: str
    ) -> None:
        """Any whitespace-only secret_access_key is rejected with INVALID_CREDENTIALS."""
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)

        assert exc_info.value.error_code == "INVALID_CREDENTIALS"
        assert exc_info.value.status_code == 400

    @given(
        access_key=whitespace_only_strategy,
        secret_key=whitespace_only_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50)
    async def test_both_whitespace_rejected(
        self, access_key: str, secret_key: str, region: str
    ) -> None:
        """Both fields whitespace-only still raises INVALID_CREDENTIALS."""
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )
        with pytest.raises(CloudSpyglassError) as exc_info:
            await manager.set_credentials(submission)

        assert exc_info.value.error_code == "INVALID_CREDENTIALS"
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Property: Valid credentials pass whitespace validation and are accepted
# ---------------------------------------------------------------------------

class TestValidCredentialsAccepted:
    """Non-whitespace access_key_id and secret_access_key pass validation."""

    @given(
        access_key=non_whitespace_strategy,
        secret_key=non_whitespace_strategy,
        region=region_strategy,
    )
    @settings(max_examples=50)
    async def test_valid_credentials_accepted(
        self, access_key: str, secret_key: str, region: str
    ) -> None:
        """Valid credentials (both non-whitespace) pass validation and are stored.

        Uses moto's mock_aws to provide a mock STS endpoint so the full
        set_credentials flow succeeds (whitespace check + STS validation).
        """
        manager = CredentialManager()
        submission = CredentialSubmission(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=None,
            region=region,
        )
        with mock_aws():
            status = await manager.set_credentials(submission)

            assert status.connected is True
            assert status.status == "Connected"
            assert status.credential_source == "ui"
