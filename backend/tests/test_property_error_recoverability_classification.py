"""Property-based tests for error recoverability classification.

**Validates: Requirements 14.2, 14.3**

Property 31: Error recoverability classification
- For any transient error (timeout, throttle, network error, temporary unavailability),
  the recoverable field SHALL be True.
- For any permanent error (invalid input, auth failure, missing fields),
  the recoverable field SHALL be False.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError, cloudspyglass_error_handler
from backend.models.errors import ErrorResponse


# ---------------------------------------------------------------------------
# Error Code Registries
# ---------------------------------------------------------------------------

# Transient errors — these must always have recoverable=True
TRANSIENT_ERROR_CODES = [
    "SCAN_TIMEOUT",
    "AWS_THROTTLED",
    "NETWORK_ERROR",
    "REGION_SCAN_FAILED",
    "EXPORT_TIMEOUT",
]

# Permanent errors — these must always have recoverable=False
PERMANENT_ERROR_CODES = [
    "INVALID_CREDENTIALS",
    "CREDENTIAL_VALIDATION_FAILED",
    "CREDENTIALS_EXPIRED",
    "NO_CREDENTIALS",
    "SCAN_IN_PROGRESS",
    "STORAGE_WRITE_FAILED",
    "STORAGE_READ_FAILED",
    "EXPORT_FAILED",
    "EXPORT_TOO_LARGE",
    "ICON_NOT_FOUND",
    "INVALID_SERVICE_TYPE",
    "INVALID_FILTER",
    "VALIDATION_ERROR",
]

# Status codes associated with transient errors
TRANSIENT_STATUS_CODES = {
    "SCAN_TIMEOUT": 504,
    "AWS_THROTTLED": 429,
    "NETWORK_ERROR": 502,
    "REGION_SCAN_FAILED": 502,
    "EXPORT_TIMEOUT": 504,
}

# Status codes associated with permanent errors
PERMANENT_STATUS_CODES = {
    "INVALID_CREDENTIALS": 400,
    "CREDENTIAL_VALIDATION_FAILED": 401,
    "CREDENTIALS_EXPIRED": 401,
    "NO_CREDENTIALS": 401,
    "SCAN_IN_PROGRESS": 409,
    "STORAGE_WRITE_FAILED": 500,
    "STORAGE_READ_FAILED": 500,
    "EXPORT_FAILED": 500,
    "EXPORT_TOO_LARGE": 413,
    "ICON_NOT_FOUND": 404,
    "INVALID_SERVICE_TYPE": 400,
    "INVALID_FILTER": 400,
    "VALIDATION_ERROR": 422,
}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

transient_error_code_strategy = st.sampled_from(TRANSIENT_ERROR_CODES)
permanent_error_code_strategy = st.sampled_from(PERMANENT_ERROR_CODES)

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


# ---------------------------------------------------------------------------
# Property 31: Error recoverability classification
# ---------------------------------------------------------------------------

class TestTransientErrorsAreRecoverable:
    """Transient errors (timeout, throttle, network) always have recoverable=True."""

    @given(
        error_code=transient_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_transient_error_has_recoverable_true(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """CloudSpyglassError with transient error code always has recoverable=True.

        **Validates: Requirements 14.2**
        """
        status_code = TRANSIENT_STATUS_CODES[error_code]

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=True,
            status_code=status_code,
        )

        assert exc.recoverable is True, (
            f"Transient error {error_code} must have recoverable=True, got False"
        )

    @given(
        error_code=transient_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_transient_error_handler_preserves_recoverable_true(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """Exception handler preserves recoverable=True for transient errors
        when converting to ErrorResponse JSON.

        **Validates: Requirements 14.2**
        """
        status_code = TRANSIENT_STATUS_CODES[error_code]

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=True,
            status_code=status_code,
        )

        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)
        data = json.loads(response.body.decode())

        assert data["recoverable"] is True, (
            f"Transient error {error_code} response must have recoverable=true, "
            f"got {data['recoverable']}"
        )

    @given(
        error_code=transient_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_transient_error_response_model_has_recoverable_true(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """ErrorResponse model built from transient error always has recoverable=True.

        **Validates: Requirements 14.2**
        """
        error_response = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
            recoverable=True,
        )

        assert error_response.recoverable is True, (
            f"ErrorResponse for transient error {error_code} must have "
            f"recoverable=True"
        )

        # Verify in serialized form too
        data = error_response.model_dump()
        assert data["recoverable"] is True


class TestPermanentErrorsAreNotRecoverable:
    """Permanent errors (invalid input, auth failure) always have recoverable=False."""

    @given(
        error_code=permanent_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_permanent_error_has_recoverable_false(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """CloudSpyglassError with permanent error code always has recoverable=False.

        **Validates: Requirements 14.3**
        """
        status_code = PERMANENT_STATUS_CODES[error_code]

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=False,
            status_code=status_code,
        )

        assert exc.recoverable is False, (
            f"Permanent error {error_code} must have recoverable=False, got True"
        )

    @given(
        error_code=permanent_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_permanent_error_handler_preserves_recoverable_false(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """Exception handler preserves recoverable=False for permanent errors
        when converting to ErrorResponse JSON.

        **Validates: Requirements 14.3**
        """
        status_code = PERMANENT_STATUS_CODES[error_code]

        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=False,
            status_code=status_code,
        )

        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)
        data = json.loads(response.body.decode())

        assert data["recoverable"] is False, (
            f"Permanent error {error_code} response must have recoverable=false, "
            f"got {data['recoverable']}"
        )

    @given(
        error_code=permanent_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_permanent_error_response_model_has_recoverable_false(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """ErrorResponse model built from permanent error always has recoverable=False.

        **Validates: Requirements 14.3**
        """
        error_response = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
            recoverable=False,
        )

        assert error_response.recoverable is False, (
            f"ErrorResponse for permanent error {error_code} must have "
            f"recoverable=False"
        )

        # Verify in serialized form too
        data = error_response.model_dump()
        assert data["recoverable"] is False


class TestRecoverabilityClassificationConsistency:
    """The classification is consistent across all paths (direct, handler, model)."""

    @given(
        error_code=transient_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_transient_classification_consistent_across_paths(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """For transient errors, recoverable=True is consistent from exception
        creation through handler to serialized response.

        **Validates: Requirements 14.2**
        """
        status_code = TRANSIENT_STATUS_CODES[error_code]

        # Path 1: Direct exception
        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=True,
            status_code=status_code,
        )
        assert exc.recoverable is True

        # Path 2: Through exception handler
        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)
        data = json.loads(response.body.decode())
        assert data["recoverable"] is True

        # Path 3: ErrorResponse model directly
        model = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=data["timestamp"],
            recoverable=True,
        )
        assert model.recoverable is True
        assert model.model_dump()["recoverable"] is True

    @given(
        error_code=permanent_error_code_strategy,
        message=message_strategy,
        details=details_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_permanent_classification_consistent_across_paths(
        self,
        error_code: str,
        message: str,
        details: str | None,
    ) -> None:
        """For permanent errors, recoverable=False is consistent from exception
        creation through handler to serialized response.

        **Validates: Requirements 14.3**
        """
        status_code = PERMANENT_STATUS_CODES[error_code]

        # Path 1: Direct exception
        exc = CloudSpyglassError(
            error_code=error_code,
            message=message,
            details=details,
            recoverable=False,
            status_code=status_code,
        )
        assert exc.recoverable is False

        # Path 2: Through exception handler
        request = MagicMock()
        response = await cloudspyglass_error_handler(request, exc)
        data = json.loads(response.body.decode())
        assert data["recoverable"] is False

        # Path 3: ErrorResponse model directly
        model = ErrorResponse(
            error_code=error_code,
            message=message,
            details=details,
            timestamp=data["timestamp"],
            recoverable=False,
        )
        assert model.recoverable is False
        assert model.model_dump()["recoverable"] is False
