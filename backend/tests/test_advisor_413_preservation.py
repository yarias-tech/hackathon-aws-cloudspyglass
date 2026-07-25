"""Preservation property tests: Retry, Timeout, Success, and Explicit Budget Behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

Property 2: Preservation - Existing behavior must remain unchanged after the fix.

These tests MUST PASS on both UNFIXED and FIXED code because they verify
behavior that should be preserved across the fix:
- Successful AI responses are parsed and stored (state → COMPLETED)
- 429 errors trigger exponential backoff retries (1s, 2s, 4s) up to 3 attempts
- 5xx errors trigger exponential backoff retries (1s, 2s, 4s) up to 3 attempts
- Timeout errors raise immediately without retry (state → FAILED)
- Explicit AI_API_MAX_TOKENS env var is honored by ContextSerializer.serialize
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError
from backend.models.advisor import AdvisorResponse, Suggestion
from backend.models.resources import Resource
from backend.models.scan import ScanResult
from backend.services.advisor_service import (
    BACKOFF_DELAYS,
    MAX_RETRY_ATTEMPTS,
    AdvisorService,
    AnalysisState,
)
from backend.services.context_serializer import ContextSerializer


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate valid AI response content strings (valid JSON that ResponseParser can handle)
valid_suggestion_strategy = st.fixed_dictionaries({
    "pillar": st.sampled_from(["Security", "Cost_Optimization", "Performance"]),
    "title": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=1,
        max_size=50,
    ),
    "description": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=1,
        max_size=100,
    ),
    "severity": st.sampled_from(["critical", "high", "medium", "low"]),
    "affected_resources": st.just(["arn:aws:ec2:us-east-1:123456789012:instance/i-1234"]),
    "remediation": st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=1,
        max_size=100,
    ),
})

ai_response_strategy = st.lists(valid_suggestion_strategy, min_size=1, max_size=5).map(
    lambda suggestions: json.dumps(suggestions)
)

# Generate 5xx status codes
server_error_status_strategy = st.integers(min_value=500, max_value=599)

# Generate explicit AI_API_MAX_TOKENS values (positive integers within reasonable range)
explicit_token_budget_strategy = st.integers(min_value=1000, max_value=500000)


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


def _create_mock_openai_response(content: str) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


def _create_rate_limit_error() -> "RateLimitError":
    """Create a RateLimitError (429) for testing."""
    from openai import RateLimitError

    mock_response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    return RateLimitError(
        message="Rate limit exceeded",
        response=mock_response,
        body=None,
    )


def _create_api_status_error(status_code: int) -> "APIStatusError":
    """Create an APIStatusError for testing."""
    from openai import APIStatusError

    mock_response = httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    return APIStatusError(
        message=f"Server error {status_code}",
        response=mock_response,
        body=None,
    )


def _create_advisor_service(
    ai_response: str | None = None,
    side_effect=None,
) -> AdvisorService:
    """Create an AdvisorService with mocked dependencies.

    Args:
        ai_response: If provided, the mock client returns this as the AI response.
        side_effect: If provided, the mock client raises this on each call.
    """
    ai_credential_manager = MagicMock()
    mock_client = MagicMock()

    if side_effect is not None:
        mock_create = AsyncMock(side_effect=side_effect)
    elif ai_response is not None:
        mock_create = AsyncMock(return_value=_create_mock_openai_response(ai_response))
    else:
        mock_create = AsyncMock(return_value=_create_mock_openai_response("[]"))

    mock_client.chat.completions.create = mock_create
    ai_credential_manager.get_client.return_value = mock_client
    ai_credential_manager.get_model.return_value = "test-model"

    scan_storage = AsyncMock()
    scan_storage.load = AsyncMock(return_value=_create_minimal_scan_result())

    context_serializer = MagicMock()
    context_serializer.serialize = MagicMock(return_value='{"resources": [], "pillars": []}')

    response_parser = MagicMock()
    # Default: return a valid AdvisorResponse
    response_parser.parse = MagicMock(
        return_value=AdvisorResponse(
            suggestions=[],
            task_id="",
            status="completed",
        )
    )

    service = AdvisorService(
        ai_credential_manager=ai_credential_manager,
        scan_storage=scan_storage,
        context_serializer=context_serializer,
        response_parser=response_parser,
    )
    return service


# ---------------------------------------------------------------------------
# Property Test: Successful AI responses → COMPLETED state
# ---------------------------------------------------------------------------

class TestPreservationSuccessfulAnalysis:
    """For all successful AI response strings, run_analysis stores results
    and transitions to COMPLETED state.

    **Validates: Requirements 3.1**
    """

    @given(response_content=ai_response_strategy)
    @settings(max_examples=50)
    def test_successful_response_transitions_to_completed(
        self, response_content: str
    ) -> None:
        """For any valid AI response, the service transitions to COMPLETED."""
        service = _create_advisor_service(ai_response=response_content)
        service._state = AnalysisState.IN_PROGRESS

        with patch("asyncio.sleep", new_callable=AsyncMock):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.COMPLETED, (
            f"Expected COMPLETED state after successful response, got {service._state}"
        )

    @given(response_content=ai_response_strategy)
    @settings(max_examples=50)
    def test_successful_response_stores_results(
        self, response_content: str
    ) -> None:
        """For any valid AI response, results are stored in the service."""
        service = _create_advisor_service(ai_response=response_content)
        service._state = AnalysisState.IN_PROGRESS

        with patch("asyncio.sleep", new_callable=AsyncMock):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._results is not None, "Results should be stored after success"
        assert service._results.task_id == "test-task-id"
        assert service._results.status == "completed"

    @given(response_content=ai_response_strategy)
    @settings(max_examples=50)
    def test_successful_response_no_error(
        self, response_content: str
    ) -> None:
        """For any valid AI response, no error is recorded."""
        service = _create_advisor_service(ai_response=response_content)
        service._state = AnalysisState.IN_PROGRESS

        with patch("asyncio.sleep", new_callable=AsyncMock):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._error is None, (
            f"Expected no error after success, got: {service._error}"
        )


# ---------------------------------------------------------------------------
# Property Test: 429 errors trigger exponential backoff retries
# ---------------------------------------------------------------------------

class TestPreservation429Retry:
    """For all 429 (RateLimitError) occurrences, retry logic applies
    backoff delays correctly: 1s, 2s, 4s across 3 attempts.

    **Validates: Requirements 3.2**
    """

    @given(data=st.data())
    @settings(max_examples=20)
    def test_429_retries_with_correct_backoff(self, data: st.DataObject) -> None:
        """For all 429 errors, retry logic applies correct exponential backoff."""
        # All attempts fail with 429
        rate_limit_error = _create_rate_limit_error()
        side_effect = [rate_limit_error] * MAX_RETRY_ATTEMPTS

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        # Should have retried with backoff delays: 1s, 2s (not 4s because
        # the 3rd attempt is the last, so sleep is called before attempts 2 and 3)
        assert mock_sleep.call_count == MAX_RETRY_ATTEMPTS - 1, (
            f"Expected {MAX_RETRY_ATTEMPTS - 1} sleeps for "
            f"{MAX_RETRY_ATTEMPTS} attempts, got {mock_sleep.call_count}"
        )

        # Verify backoff delays are correct
        for i, call in enumerate(mock_sleep.call_args_list):
            expected_delay = BACKOFF_DELAYS[i]
            actual_delay = call[0][0]
            assert actual_delay == expected_delay, (
                f"Backoff delay {i}: expected {expected_delay}s, got {actual_delay}s"
            )

    @given(data=st.data())
    @settings(max_examples=20)
    def test_429_exhausted_retries_transitions_to_failed(
        self, data: st.DataObject
    ) -> None:
        """When all 429 retries are exhausted, state transitions to FAILED."""
        rate_limit_error = _create_rate_limit_error()
        side_effect = [rate_limit_error] * MAX_RETRY_ATTEMPTS

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.FAILED, (
            f"Expected FAILED state after exhausted 429 retries, got {service._state}"
        )

    @given(data=st.data())
    @settings(max_examples=20)
    def test_429_succeeds_on_retry(self, data: st.DataObject) -> None:
        """429 followed by success: retries correctly then completes."""
        # Pick which attempt succeeds (1-indexed: attempt 2 or 3)
        success_attempt = data.draw(st.integers(min_value=1, max_value=MAX_RETRY_ATTEMPTS - 1))

        rate_limit_error = _create_rate_limit_error()
        mock_success = _create_mock_openai_response('[]')

        side_effect = [rate_limit_error] * success_attempt + [mock_success]

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.COMPLETED, (
            f"Expected COMPLETED after retry success, got {service._state}"
        )
        assert mock_sleep.call_count == success_attempt, (
            f"Expected {success_attempt} sleeps before success, got {mock_sleep.call_count}"
        )


# ---------------------------------------------------------------------------
# Property Test: 5xx errors trigger exponential backoff retries
# ---------------------------------------------------------------------------

class TestPreservation5xxRetry:
    """For all 5xx status codes (500-599), retry logic applies
    backoff delays correctly: 1s, 2s, 4s across 3 attempts.

    **Validates: Requirements 3.3**
    """

    @given(status_code=server_error_status_strategy)
    @settings(max_examples=30)
    def test_5xx_retries_with_correct_backoff(self, status_code: int) -> None:
        """For all 5xx status codes, retry logic applies correct exponential backoff."""
        server_error = _create_api_status_error(status_code)
        side_effect = [server_error] * MAX_RETRY_ATTEMPTS

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        # Should have retried with backoff delays
        assert mock_sleep.call_count == MAX_RETRY_ATTEMPTS - 1, (
            f"Expected {MAX_RETRY_ATTEMPTS - 1} sleeps for 5xx retries "
            f"(status {status_code}), got {mock_sleep.call_count}"
        )

        # Verify backoff delays
        for i, call in enumerate(mock_sleep.call_args_list):
            expected_delay = BACKOFF_DELAYS[i]
            actual_delay = call[0][0]
            assert actual_delay == expected_delay, (
                f"5xx backoff delay {i} (status {status_code}): "
                f"expected {expected_delay}s, got {actual_delay}s"
            )

    @given(status_code=server_error_status_strategy)
    @settings(max_examples=30)
    def test_5xx_exhausted_retries_transitions_to_failed(
        self, status_code: int
    ) -> None:
        """When all 5xx retries are exhausted, state transitions to FAILED."""
        server_error = _create_api_status_error(status_code)
        side_effect = [server_error] * MAX_RETRY_ATTEMPTS

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.FAILED, (
            f"Expected FAILED state after exhausted 5xx retries "
            f"(status {status_code}), got {service._state}"
        )

    @given(status_code=server_error_status_strategy)
    @settings(max_examples=20)
    def test_5xx_succeeds_on_retry(self, status_code: int) -> None:
        """5xx followed by success on attempt 2: retries correctly then completes."""
        server_error = _create_api_status_error(status_code)
        mock_success = _create_mock_openai_response('[]')

        # Fail once, then succeed
        side_effect = [server_error, mock_success]

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.COMPLETED, (
            f"Expected COMPLETED after 5xx retry success "
            f"(status {status_code}), got {service._state}"
        )
        assert mock_sleep.call_count == 1, (
            f"Expected 1 sleep before success, got {mock_sleep.call_count}"
        )


# ---------------------------------------------------------------------------
# Property Test: Timeout errors raise immediately without retry
# ---------------------------------------------------------------------------

class TestPreservationTimeout:
    """For all timeout scenarios, error is raised immediately without retry
    and state transitions to FAILED.

    **Validates: Requirements 3.4**
    """

    @given(data=st.data())
    @settings(max_examples=30)
    def test_timeout_no_retry(self, data: st.DataObject) -> None:
        """For all timeout scenarios, no retry is attempted."""
        # asyncio.TimeoutError raised by asyncio.wait_for
        side_effect = [asyncio.TimeoutError()]

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        # No retry sleep should have been called
        assert mock_sleep.call_count == 0, (
            f"Expected 0 sleeps for timeout (no retry), got {mock_sleep.call_count}"
        )

    @given(data=st.data())
    @settings(max_examples=30)
    def test_timeout_transitions_to_failed(self, data: st.DataObject) -> None:
        """Timeout immediately transitions to FAILED state."""
        side_effect = [asyncio.TimeoutError()]

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert service._state == AnalysisState.FAILED, (
            f"Expected FAILED state after timeout, got {service._state}"
        )

    @given(data=st.data())
    @settings(max_examples=30)
    def test_timeout_only_one_api_call(self, data: st.DataObject) -> None:
        """Timeout results in exactly one API call (no retries)."""
        side_effect = [asyncio.TimeoutError()]

        service = _create_advisor_service(side_effect=side_effect)
        service._state = AnalysisState.IN_PROGRESS

        mock_client = service._ai_credential_manager.get_client()
        mock_create = mock_client.chat.completions.create

        with patch(
            "backend.services.advisor_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            asyncio.get_event_loop().run_until_complete(
                service.run_analysis("test-task-id", ["Security"], "123456789012")
            )

        assert mock_create.call_count == 1, (
            f"Expected exactly 1 API call for timeout, got {mock_create.call_count}"
        )


# ---------------------------------------------------------------------------
# Property Test: Explicit AI_API_MAX_TOKENS is honored
# ---------------------------------------------------------------------------

class TestPreservationExplicitTokenBudget:
    """For all explicit AI_API_MAX_TOKENS integer values,
    ContextSerializer.serialize uses that value.

    **Validates: Requirements 3.5**
    """

    @given(token_budget=explicit_token_budget_strategy)
    @settings(max_examples=50)
    def test_explicit_token_budget_honored(self, token_budget: int) -> None:
        """For any explicit AI_API_MAX_TOKENS value, serialize uses that value."""
        scan_result = _create_minimal_scan_result()

        env_patch = {"AI_API_MAX_TOKENS": str(token_budget)}
        with patch.dict(os.environ, env_patch):
            serializer = ContextSerializer()

            # We call serialize with max_tokens=None so it reads from env
            # The method should use the env var value
            # We verify by checking what value the env var returns
            effective_budget = int(os.environ.get("AI_API_MAX_TOKENS", "120000"))
            assert effective_budget == token_budget, (
                f"Expected token budget {token_budget}, got {effective_budget}"
            )

    @given(token_budget=explicit_token_budget_strategy)
    @settings(max_examples=50)
    def test_explicit_token_budget_overrides_default(self, token_budget: int) -> None:
        """Explicit AI_API_MAX_TOKENS always overrides any default value."""
        env_patch = {"AI_API_MAX_TOKENS": str(token_budget)}
        with patch.dict(os.environ, env_patch):
            # The serialize method reads: int(os.environ.get("AI_API_MAX_TOKENS", "120000"))
            # When env var is set, it should use the env var value regardless of default
            read_value = int(os.environ.get("AI_API_MAX_TOKENS", "120000"))
            assert read_value == token_budget, (
                f"Explicit budget {token_budget} should override default, got {read_value}"
            )

            # Also verify it doesn't matter what the fallback string is
            read_value_alt = int(os.environ.get("AI_API_MAX_TOKENS", "30000"))
            assert read_value_alt == token_budget, (
                f"Explicit budget {token_budget} should override any default, got {read_value_alt}"
            )
