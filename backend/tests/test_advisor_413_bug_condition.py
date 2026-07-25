"""Bug condition exploration test: CloudSpyglassError details lost in logging.

**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**

Property 1: Bug Condition - CloudSpyglassError Details Lost in Logging

This test is EXPECTED TO FAIL on unfixed code. Failure confirms the bug exists:
- The `run_analysis` catch-all logs only `str(exc)` which discards the `details` field
- The default token budget is 120,000 (too high for many providers)

When the fix is applied, these tests will PASS (confirming the fix works).
"""

import asyncio
import logging
import logging.handlers
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError
from backend.models.resources import Relationship, Resource
from backend.models.scan import ScanResult
from backend.services.advisor_service import AdvisorService, AnalysisState
from backend.services.context_serializer import ContextSerializer


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate non-empty details strings that simulate real API error messages
details_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=5,
    max_size=200,
).filter(lambda s: s.strip())

# Realistic details strings like what a 413 error would contain
realistic_details_strategy = st.one_of(
    st.just("Maximum context length exceeded: 131072 tokens > 32768 max"),
    st.just("Request body too large: 512000 bytes exceeds 65536 limit"),
    st.just("This model's maximum context length is 32768 tokens. You provided 131072 tokens."),
    details_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_minimal_scan_result() -> ScanResult:
    """Create a minimal ScanResult for testing."""
    return ScanResult(
        account_id="123456789012",
        scan_timestamp="2024-01-01T00:00:00Z",
        resources=[
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234",
                resource_type="ec2",
                name="test-instance",
                region="us-east-1",
            )
        ],
        relationships=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1000,
    )


def _create_advisor_service_with_mocks(
    raise_error: CloudSpyglassError,
) -> AdvisorService:
    """Create an AdvisorService with mocked dependencies that raise the given error.

    The context_serializer.serialize is mocked to raise the given
    CloudSpyglassError, simulating a failure in the analysis pipeline.
    """
    ai_credential_manager = MagicMock()
    scan_storage = AsyncMock()
    scan_storage.load = AsyncMock(return_value=_create_minimal_scan_result())
    context_serializer = MagicMock()
    context_serializer.serialize = MagicMock(side_effect=raise_error)
    response_parser = MagicMock()

    service = AdvisorService(
        ai_credential_manager=ai_credential_manager,
        scan_storage=scan_storage,
        context_serializer=context_serializer,
        response_parser=response_parser,
    )
    return service


# ---------------------------------------------------------------------------
# Property Test: Details ARE present in log output (will FAIL on unfixed code)
# ---------------------------------------------------------------------------

class TestBugConditionDetailsLostInLogging:
    """For any CloudSpyglassError with non-null details caught in run_analysis,
    the log output SHOULD contain the details string.

    On UNFIXED code, this test FAILS — confirming the bug exists.
    On FIXED code, this test PASSES — confirming the fix works.
    """

    @given(details=realistic_details_strategy)
    @settings(max_examples=50)
    def test_details_present_in_log_output(self, details: str) -> None:
        """Assert that details content IS present in the captured log output.

        This will FAIL on unfixed code because `run_analysis` logs only
        `str(exc)` which is the `message` field, not `details`.
        """
        error = CloudSpyglassError(
            error_code="AI_CLIENT_ERROR",
            message="AI API rejected the request with status 413.",
            details=details,
            recoverable=False,
            status_code=502,
        )

        service = _create_advisor_service_with_mocks(raise_error=error)
        # Force the service into IN_PROGRESS state so run_analysis proceeds
        service._state = AnalysisState.IN_PROGRESS

        # Use a log handler directly (avoids caplog fixture incompatibility with Hypothesis)
        log_handler = logging.handlers.MemoryHandler(capacity=1000)
        log_handler.setLevel(logging.ERROR)
        advisor_logger = logging.getLogger("backend.services.advisor_service")
        advisor_logger.addHandler(log_handler)
        advisor_logger.setLevel(logging.ERROR)

        try:
            asyncio.new_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

            # Collect log output from the handler's buffer
            log_text = ""
            for record in log_handler.buffer:
                log_text += advisor_logger.handlers[0].format(record) if hasattr(record, 'msg') else ""
                log_text += record.getMessage() + "\n"

            # Assert: details SHOULD be in the log output
            # On unfixed code, this assertion FAILS (details are lost)
            assert details in log_text, (
                f"Bug confirmed: details field is NOT present in log output.\n"
                f"Expected to find: {details!r}\n"
                f"Actual log output: {log_text!r}\n"
                f"Only the wrapper message is logged, details are lost."
            )
        finally:
            advisor_logger.removeHandler(log_handler)

    @given(details=realistic_details_strategy)
    @settings(max_examples=50)
    def test_details_present_in_error_field(self, details: str) -> None:
        """Assert that details content IS present in the service._error field.

        This will FAIL on unfixed code because `self._error = str(exc)`
        only captures the message, not details.
        """
        error = CloudSpyglassError(
            error_code="AI_CLIENT_ERROR",
            message="AI API rejected the request with status 413.",
            details=details,
            recoverable=False,
            status_code=502,
        )

        service = _create_advisor_service_with_mocks(raise_error=error)
        service._state = AnalysisState.IN_PROGRESS

        asyncio.new_event_loop().run_until_complete(
            service.run_analysis("test-task-id", ["Security"], "123456789012")
        )

        # Assert: details SHOULD be in the stored _error field
        # On unfixed code, this assertion FAILS (only str(exc) = message is stored)
        assert details in service._error, (
            f"Bug confirmed: details field is NOT present in service._error.\n"
            f"Expected _error to contain: {details!r}\n"
            f"Actual _error value: {service._error!r}\n"
            f"Only str(exc) is stored, which is just the message field."
        )


# ---------------------------------------------------------------------------
# Test: Default token budget is too high (confirms problematic default)
# ---------------------------------------------------------------------------

class TestBugConditionDefaultTokenBudget:
    """The default token budget SHOULD be 30,000 (safe for most providers).

    On UNFIXED code, this test FAILS — confirming the default is 120,000.
    On FIXED code, this test PASSES — confirming the new default of 30,000.
    """

    def test_default_token_budget_is_safe(self) -> None:
        """Assert that default token budget is 30,000 when AI_API_MAX_TOKENS is unset.

        On unfixed code, the default is 120,000 which exceeds many provider limits.
        This test will FAIL on unfixed code, confirming the problematic default.
        """
        # Ensure AI_API_MAX_TOKENS is not set
        env_without_token_var = {
            k: v for k, v in os.environ.items() if k != "AI_API_MAX_TOKENS"
        }

        with patch.dict(os.environ, env_without_token_var, clear=True):
            # Track what default value the serializer uses when reading AI_API_MAX_TOKENS
            original_get = os.environ.get
            captured_defaults: list[str] = []

            def tracking_get(key: str, default: str | None = None) -> str | None:
                if key == "AI_API_MAX_TOKENS":
                    captured_defaults.append(default)
                return original_get(key, default)

            with patch.object(os.environ, "get", side_effect=tracking_get):
                serializer = ContextSerializer()
                scan_result = _create_minimal_scan_result()
                serializer.serialize(scan_result, ["Security"])

            # Assert: the serializer's fallback default SHOULD be "30000"
            # On unfixed code, this FAILS because the fallback is "120000"
            assert len(captured_defaults) == 1, (
                "Expected serialize to read AI_API_MAX_TOKENS exactly once"
            )
            assert captured_defaults[0] == "30000", (
                f"Bug confirmed: default token budget is '{captured_defaults[0]}', "
                f"expected '30000'. The current default exceeds many provider limits."
            )
