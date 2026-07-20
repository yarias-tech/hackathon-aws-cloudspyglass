"""Property-based tests for credential replacement.

**Validates: Requirements 1.4**

Property 2: Credential replacement
- For any sequence of valid credential submissions, the `get_boto3_session()` method
  SHALL always return a session configured with the most recently submitted credentials,
  and no previously submitted credential SHALL remain active.
"""

import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from backend.models.credentials import CredentialSubmission
from backend.services.credential_manager import CredentialManager


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

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

# Strategy: a valid credential submission tuple (access_key, secret_key, region)
credential_strategy = st.tuples(
    non_whitespace_strategy,
    non_whitespace_strategy,
    region_strategy,
)

# Strategy: a non-empty list of credential submissions (sequences of 2 to 10)
credential_sequence_strategy = st.lists(
    credential_strategy,
    min_size=2,
    max_size=10,
)


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
# Property 2: Credential replacement — latest credentials are always active
# ---------------------------------------------------------------------------

class TestCredentialReplacement:
    """Sequential credential submissions always result in latest being active."""

    @given(credentials=credential_sequence_strategy)
    @settings(max_examples=50, deadline=None)
    async def test_latest_credentials_are_active(
        self, credentials: list[tuple[str, str, str]]
    ) -> None:
        """After submitting N credentials sequentially, get_boto3_session() returns
        a session configured with the LAST submitted credentials only.

        **Validates: Requirements 1.4**
        """
        manager = CredentialManager()

        with mock_aws():
            # Submit all credentials sequentially
            for access_key, secret_key, region in credentials:
                submission = CredentialSubmission(
                    access_key_id=access_key,
                    secret_access_key=secret_key,
                    session_token=None,
                    region=region,
                )
                await manager.set_credentials(submission)

            # After all submissions, get the active session
            session = await manager.get_boto3_session()

            # The session should use the LAST submitted credentials
            last_access_key, last_secret_key, last_region = credentials[-1]

            session_credentials = session.get_credentials().get_frozen_credentials()
            assert session_credentials.access_key == last_access_key.strip()
            assert session_credentials.secret_key == last_secret_key.strip()
            assert session.region_name == last_region

    @given(credentials=credential_sequence_strategy)
    @settings(max_examples=50, deadline=None)
    async def test_no_previous_credentials_remain(
        self, credentials: list[tuple[str, str, str]]
    ) -> None:
        """After submitting N credentials, no previously submitted credential
        (other than the last) remains in the manager's state.

        **Validates: Requirements 1.4**
        """
        manager = CredentialManager()

        with mock_aws():
            # Submit all credentials sequentially
            for access_key, secret_key, region in credentials:
                submission = CredentialSubmission(
                    access_key_id=access_key,
                    secret_access_key=secret_key,
                    session_token=None,
                    region=region,
                )
                await manager.set_credentials(submission)

            # Verify intermediate credentials are NOT active
            session = await manager.get_boto3_session()
            session_credentials = session.get_credentials().get_frozen_credentials()

            # Check that none of the intermediate credentials are active
            for access_key, secret_key, _region in credentials[:-1]:
                # If intermediate credentials happen to be the same as the last,
                # skip the check (they'd match legitimately)
                if (access_key.strip() == credentials[-1][0].strip()
                        and secret_key.strip() == credentials[-1][1].strip()):
                    continue
                # At least one of access_key or secret_key should differ from active
                intermediate_matches = (
                    session_credentials.access_key == access_key.strip()
                    and session_credentials.secret_key == secret_key.strip()
                )
                assert not intermediate_matches, (
                    f"Intermediate credential (access_key={access_key!r}) "
                    f"is still active after replacement"
                )

    @given(
        first_cred=credential_strategy,
        second_cred=credential_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_single_replacement_uses_latest(
        self, first_cred: tuple[str, str, str], second_cred: tuple[str, str, str]
    ) -> None:
        """A simple two-credential sequence confirms the second always wins.

        **Validates: Requirements 1.4**
        """
        manager = CredentialManager()

        with mock_aws():
            # Submit first credentials
            submission_1 = CredentialSubmission(
                access_key_id=first_cred[0],
                secret_access_key=first_cred[1],
                session_token=None,
                region=first_cred[2],
            )
            await manager.set_credentials(submission_1)

            # Submit second credentials (replacement)
            submission_2 = CredentialSubmission(
                access_key_id=second_cred[0],
                secret_access_key=second_cred[1],
                session_token=None,
                region=second_cred[2],
            )
            await manager.set_credentials(submission_2)

            # Verify session uses ONLY the second credentials
            session = await manager.get_boto3_session()
            session_credentials = session.get_credentials().get_frozen_credentials()

            assert session_credentials.access_key == second_cred[0].strip()
            assert session_credentials.secret_key == second_cred[1].strip()
            assert session.region_name == second_cred[2]
