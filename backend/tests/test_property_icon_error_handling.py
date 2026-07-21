"""Property-based tests for icon error handling.

**Validates: Requirements 13.6, 13.7**

Property 29: Icon error handling
- Test that unknown service_type returns 400 and missing file returns 404,
  both with standard error structure.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.routes.images import ICON_PATH_MAP, KNOWN_RESOURCE_TYPES

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: generate strings that are NOT in KNOWN_RESOURCE_TYPES
# Use alphabetic strings of length 1-30, then filter out any that happen to match
_unknown_service_type_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu"), whitelist_characters="_"),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in KNOWN_RESOURCE_TYPES)

# Strategy: pick from known resource types (for 404 testing with missing files)
_valid_service_types_list = sorted(KNOWN_RESOURCE_TYPES)
_valid_service_type_strategy = st.sampled_from(_valid_service_types_list)

# ISO 8601 UTC timestamp pattern
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_error_response_structure(body: dict) -> None:
    """Assert the response body conforms to the standard error structure."""
    # All required fields must be present
    assert "error_code" in body, "Missing 'error_code' field"
    assert "message" in body, "Missing 'message' field"
    assert "details" in body, "Missing 'details' field"
    assert "timestamp" in body, "Missing 'timestamp' field"
    assert "recoverable" in body, "Missing 'recoverable' field"

    # error_code must be UPPER_SNAKE_CASE string
    assert isinstance(body["error_code"], str)
    assert body["error_code"] == body["error_code"].upper()
    assert re.match(r"^[A-Z][A-Z0-9_]*$", body["error_code"]), (
        f"error_code '{body['error_code']}' is not UPPER_SNAKE_CASE"
    )

    # message must be a string ≤500 chars
    assert isinstance(body["message"], str)
    assert len(body["message"]) <= 500, (
        f"message length {len(body['message'])} exceeds 500 chars"
    )

    # details must be string or null
    assert body["details"] is None or isinstance(body["details"], str)

    # timestamp must be ISO 8601 UTC
    assert isinstance(body["timestamp"], str)
    assert _ISO8601_PATTERN.match(body["timestamp"]), (
        f"timestamp '{body['timestamp']}' does not match ISO 8601 UTC format"
    )

    # recoverable must be a boolean
    assert isinstance(body["recoverable"], bool)


# ---------------------------------------------------------------------------
# Property 29a: Unknown service_type → 400 INVALID_SERVICE_TYPE
# ---------------------------------------------------------------------------


class TestIconErrorUnknownServiceType:
    """Unknown service_type returns 400 with INVALID_SERVICE_TYPE error."""

    @given(service_type=_unknown_service_type_strategy)
    @settings(max_examples=50)
    async def test_unknown_service_type_returns_400(self, service_type: str) -> None:
        """For any string NOT in KNOWN_RESOURCE_TYPES, the endpoint returns
        HTTP 400 with a JSON body matching the standard error response structure.

        **Validates: Requirements 13.7**
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/images/icons/{service_type}")

        # Must return 400
        assert response.status_code == 400, (
            f"Expected 400 for unknown service_type '{service_type}', "
            f"got {response.status_code}"
        )

        # Response must be valid JSON
        body = response.json()

        # Validate standard error structure
        _validate_error_response_structure(body)

        # Specific checks for this error case
        assert body["error_code"] == "INVALID_SERVICE_TYPE", (
            f"Expected error_code 'INVALID_SERVICE_TYPE', got '{body['error_code']}'"
        )
        assert body["recoverable"] is False, (
            "Expected recoverable=False for invalid service type"
        )


# ---------------------------------------------------------------------------
# Property 29b: Valid service_type with missing file → 404 ICON_NOT_FOUND
# ---------------------------------------------------------------------------


class TestIconErrorMissingFile:
    """Valid service_type with missing icon file returns 404 with ICON_NOT_FOUND."""

    @given(service_type=_valid_service_type_strategy)
    @settings(max_examples=50)
    async def test_missing_icon_file_returns_404(self, service_type: str) -> None:
        """For any valid service_type where the icon file does not exist on disk,
        the endpoint returns HTTP 404 with a JSON body matching the standard
        error response structure.

        **Validates: Requirements 13.6**
        """
        # Create a patched ICON_PATH_MAP where the file path points to a
        # non-existent location, simulating a missing icon file
        fake_path = Path("/nonexistent/path/to/icon.svg")
        patched_map = {**ICON_PATH_MAP, service_type: fake_path}

        with patch("backend.routes.images.ICON_PATH_MAP", patched_map):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(f"/api/images/icons/{service_type}")

        # Must return 404
        assert response.status_code == 404, (
            f"Expected 404 for '{service_type}' with missing file, "
            f"got {response.status_code}"
        )

        # Response must be valid JSON
        body = response.json()

        # Validate standard error structure
        _validate_error_response_structure(body)

        # Specific checks for this error case
        assert body["error_code"] == "ICON_NOT_FOUND", (
            f"Expected error_code 'ICON_NOT_FOUND', got '{body['error_code']}'"
        )
        assert body["recoverable"] is False, (
            "Expected recoverable=False for missing icon file"
        )
