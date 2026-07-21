"""Property-based tests for error response structure invariant.

**Validates: Requirements 14.1**

Property 30: Error response structure invariant
- For any error response returned by any CloudSpyglass API endpoint, the JSON body
  SHALL contain exactly these fields: error_code (string, UPPER_SNAKE_CASE),
  message (string, ≤500 characters), details (string or null),
  timestamp (ISO 8601 UTC string), and recoverable (boolean).
"""

import re
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from backend.exceptions import CloudSpyglassError, cloudspyglass_error_handler
from backend.main import app
from backend.models.errors import ErrorResponse


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: valid UPPER_SNAKE_CASE error codes (matching known project codes)
known_error_codes = st.sampled_from([
    "INVALID_CREDENTIALS",
    "CREDENTIAL_VALIDATION_FAILED",
    "CREDENTIALS_EXPIRED",
    "NO_CREDENTIALS",
    "SCAN_IN_PROGRESS",
    "SCAN_TIMEOUT",
    "REGION_SCAN_FAILED",
    "AWS_THROTTLED",
    "NETWORK_ERROR",
    "STORAGE_WRITE_FAILED",
    "STORAGE_READ_FAILED",
    "EXPORT_FAILED",
    "EXPORT_TOO_LARGE",
    "EXPORT_TIMEOUT",
    "ICON_NOT_FOUND",
    "INVALID_SERVICE_TYPE",
    "INVALID_FILTER",
    "VALIDATION_ERROR",
])

# Strategy: arbitrary UPPER_SNAKE_CASE strings for error_code
arbitrary_error_codes = st.from_regex(r"[A-Z][A-Z0-9_]{0,49}", fullmatch=True)

# Strategy: error messages (non-empty, ≤500 chars)
message_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=500,
).filter(lambda s: s.strip() != "")

# Strategy: details field (string or None)
details_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
        min_size=0,
        max_size=200,
    ),
)

# Strategy: recoverable boolean
recoverable_strategy = st.booleans()

# Strategy: valid HTTP status codes for errors
status_code_strategy = st.integers(min_value=400, max_value=599)

# Strategy: ISO 8601 UTC timestamps
timestamp_strategy = st.builds(
    lambda dt: dt.isoformat(),
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UPPER_SNAKE_CASE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def assert_error_response_fields(data: dict) -> None:
    """Assert the response dict has exactly the 5 required fields with correct types."""
    required_fields = {"error_code", "message", "details", "timestamp", "recoverable"}
    assert set(data.keys()) == required_fields, (
        f"Expected exactly {required_fields}, got {set(data.keys())}"
    )

    # error_code must be UPPER_SNAKE_CASE
    assert isinstance(data["error_code"], str)
    assert UPPER_SNAKE_CASE_RE.match(data["error_code"]), (
        f"error_code '{data['error_code']}' is not UPPER_SNAKE_CASE"
    )

    # message must be ≤500 characters
    assert isinstance(data["message"], str)
    assert len(data["message"]) <= 500, (
        f"message length {len(data['message'])} exceeds 500 chars"
    )

    # details must be string or null
    assert data["details"] is None or isinstance(data["details"], str), (
        f"details must be string or null, got {type(data['details'])}"
    )

    # timestamp must be valid ISO 8601
    assert isinstance(data["timestamp"], str)
    try:
        datetime.fromisoformat(data["timestamp"])
    except ValueError:
        pytest.fail(f"timestamp '{data['timestamp']}' is not valid ISO 8601")

    # recoverable must be boolean
    assert isinstance(data["recoverable"], bool), (
        f"recoverable must be boolean, got {type(data['recoverable'])}"
    )


# ---------------------------------------------------------------------------
# Property 30: Error response structure invariant
# ---------------------------------------------------------------------------

class TestErrorResponseModelStructure:
    """ErrorResponse model always produces exactly the 5 required fields."""

    @given(
        error_code=arbitrary_error_codes,
        message=message_strategy,
        details=details_strategy,
        timestamp=timestamp_strategy,
        recoverable=recoverable_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_model_always_contains_exactly_five_fields(
        self,
        error_code: str,
        message: str,
        details: str | None,
        timestamp: str,
        recoverable: bool,
    ) -> None:
        """Direct model instantiation always produces a dict with exactly the
        5 required fields: error_code, message, details, timestamp, recoverable.

        **Validates: Requirements 14.1**
        """
        response = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=timestamp,
            recoverable=recoverable,
        )
        data = response.model_dump()

        assert_error_response_fields(data)

    @given(
        error_code=arbitrary_error_codes,
        message=message_strategy,
        details=details_strategy,
        timestamp=timestamp_strategy,
        recoverable=recoverable_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_error_code_is_always_upper_snake_case(
        self,
        error_code: str,
        message: str,
        details: str | None,
        timestamp: str,
        recoverable: bool,
    ) -> None:
        """error_code field always matches UPPER_SNAKE_CASE regex pattern.

        **Validates: Requirements 14.1**
        """
        response = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=timestamp,
            recoverable=recoverable,
        )
        assert UPPER_SNAKE_CASE_RE.match(response.error_code), (
            f"error_code '{response.error_code}' is not UPPER_SNAKE_CASE"
        )

    @given(
        error_code=known_error_codes,
        message=message_strategy,
        details=details_strategy,
        recoverable=recoverable_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_timestamp_is_always_valid_iso8601(
        self,
        error_code: str,
        message: str,
        details: str | None,
        recoverable: bool,
    ) -> None:
        """timestamp field is always a valid ISO 8601 UTC string when generated
        by the error handler's datetime.now(timezone.utc).isoformat().

        **Validates: Requirements 14.1**
        """
        ts = datetime.now(timezone.utc).isoformat()
        response = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=ts,
            recoverable=recoverable,
        )
        # Must parse without error
        parsed = datetime.fromisoformat(response.timestamp)
        # Must be timezone-aware (UTC)
        assert parsed.tzinfo is not None

    @given(
        error_code=known_error_codes,
        details=details_strategy,
        recoverable=recoverable_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_message_never_exceeds_500_chars(
        self,
        error_code: str,
        details: str | None,
        recoverable: bool,
    ) -> None:
        """Messages exceeding 500 characters are rejected by the model.

        **Validates: Requirements 14.1**
        """
        long_message = "A" * 501
        with pytest.raises(ValidationError):
            ErrorResponse(
                error_code=error_code,
                message=long_message,
                details=details,
                timestamp=datetime.now(timezone.utc).isoformat(),
                recoverable=recoverable,
            )

    @given(
        error_code=known_error_codes,
        message=message_strategy,
        recoverable=recoverable_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_details_is_always_string_or_null(
        self,
        error_code: str,
        message: str,
        recoverable: bool,
    ) -> None:
        """details field is always either a string or None (null in JSON).

        **Validates: Requirements 14.1**
        """
        # Test with None
        response_null = ErrorResponse(
            error_code=error_code,
            message=message,
            details=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            recoverable=recoverable,
        )
        assert response_null.details is None

        # Test with a string
        response_str = ErrorResponse(
            error_code=error_code,
            message=message,
            details="Some detail info",
            timestamp=datetime.now(timezone.utc).isoformat(),
            recoverable=recoverable,
        )
        assert isinstance(response_str.details, str)


class TestExceptionHandlerStructure:
    """CloudSpyglassError → exception handler always produces correct structure."""

    @given(
        error_code=known_error_codes,
        message=message_strategy,
        details=details_strategy,
        recoverable=recoverable_strategy,
        status_code=status_code_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_handler_produces_correct_json_structure(
        self,
        error_code: str,
        message: str,
        details: str | None,
        recoverable: bool,
        status_code: int,
    ) -> None:
        """The exception handler always produces a JSON body with exactly the
        5 required fields in correct types.

        **Validates: Requirements 14.1**
        """
        from unittest.mock import MagicMock

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=recoverable,
            status_code=status_code,
        )

        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)

        import json
        data = json.loads(response.body.decode())

        assert_error_response_fields(data)
        assert response.status_code == status_code

    @given(
        error_code=known_error_codes,
        message=message_strategy,
        details=details_strategy,
        recoverable=recoverable_strategy,
        status_code=status_code_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_handler_preserves_all_input_values(
        self,
        error_code: str,
        message: str,
        details: str | None,
        recoverable: bool,
        status_code: int,
    ) -> None:
        """The exception handler correctly maps all exception fields to the
        JSON response body.

        **Validates: Requirements 14.1**
        """
        from unittest.mock import MagicMock

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=recoverable,
            status_code=status_code,
        )

        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)

        import json
        data = json.loads(response.body.decode())

        assert data["error_code"] == error_code
        assert data["message"] == message
        assert data["details"] == details
        assert data["recoverable"] == recoverable


class TestHTTPEndpointErrorStructure:
    """HTTP error responses from real endpoints always conform to the structure."""

    @given(
        service_type=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=1,
            max_size=30,
        ).filter(lambda s: s not in {
            "ec2", "vpc", "s3", "lambda", "rds", "iam", "dynamodb",
            "ecs", "eks", "sns", "sqs", "cloudfront", "elasticache",
            "elasticsearch", "redshift", "kinesis", "apigateway",
        }),
    )
    @settings(max_examples=50, deadline=None)
    async def test_invalid_icon_request_returns_structured_error(
        self,
        service_type: str,
    ) -> None:
        """GET /api/images/icons/{invalid_service_type} returns a response
        with exactly the 5 required error fields.

        **Validates: Requirements 14.1**
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/images/icons/{service_type}")

            # Only check error responses (4xx/5xx)
            if response.status_code >= 400:
                data = response.json()
                assert_error_response_fields(data)
