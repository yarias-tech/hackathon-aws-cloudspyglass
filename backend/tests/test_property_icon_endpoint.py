"""Property-based tests for icon endpoint correctness.

**Validates: Requirements 13.2**

Property 28: Icon endpoint correctness
- For any valid service_type from KNOWN_RESOURCE_TYPES that has an existing SVG
  file on disk, the GET /api/images/icons/{service_type} endpoint SHALL return
  HTTP 200 with Content-Type image/svg+xml and non-empty SVG content.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.routes.images import ICON_PATH_MAP, KNOWN_RESOURCE_TYPES

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Determine which service types have actual SVG files on disk
_VALID_TYPES_WITH_FILES = sorted(
    svc
    for svc in KNOWN_RESOURCE_TYPES
    if svc in ICON_PATH_MAP and ICON_PATH_MAP[svc].is_file()
)

# Guard: skip the entire module if no icon files are present on disk
pytestmark = pytest.mark.skipif(
    len(_VALID_TYPES_WITH_FILES) == 0,
    reason="No SVG icon files found on disk — cannot test icon endpoint",
)

# Strategy: pick from service types that have existing icon files
valid_service_type_strategy = st.sampled_from(_VALID_TYPES_WITH_FILES)


# ---------------------------------------------------------------------------
# Property 28: Icon endpoint correctness
# ---------------------------------------------------------------------------


class TestIconEndpointCorrectness:
    """Valid service_type with existing SVG returns 200 with image/svg+xml."""

    @given(service_type=valid_service_type_strategy)
    @settings(max_examples=50)
    async def test_valid_service_type_returns_svg(self, service_type: str) -> None:
        """For any valid service_type with an existing SVG file, the endpoint
        returns HTTP 200, Content-Type image/svg+xml, and non-empty SVG content.

        **Validates: Requirements 13.2**
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/images/icons/{service_type}")

        # HTTP 200 status
        assert response.status_code == 200, (
            f"Expected 200 for '{service_type}', got {response.status_code}"
        )

        # Content-Type must be image/svg+xml
        content_type = response.headers.get("content-type", "")
        assert "image/svg+xml" in content_type, (
            f"Expected 'image/svg+xml' in Content-Type for '{service_type}', "
            f"got '{content_type}'"
        )

        # Response body must be non-empty and contain SVG markers
        body = response.text
        assert len(body) > 0, (
            f"Response body is empty for '{service_type}'"
        )
        assert "<" in body, (
            f"Response body for '{service_type}' does not appear to contain XML/SVG content"
        )
        # Check for SVG-specific markers (svg tag or XML declaration)
        has_svg_marker = "<svg" in body.lower() or "<?xml" in body.lower()
        assert has_svg_marker, (
            f"Response body for '{service_type}' does not contain SVG or XML markers"
        )
