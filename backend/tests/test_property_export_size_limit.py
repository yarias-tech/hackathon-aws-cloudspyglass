"""Property-based tests for export size limit enforcement.

**Validates: Requirements 11.6**

Property 26: Export size limit enforcement
- Test that exports exceeding 50 MB are rejected without producing a file.
- For ANY content size exceeding 50 MB, _check_size_limit MUST raise CloudSpyglassError
  with error_code="EXPORT_TOO_LARGE", status_code=413, and recoverable=False.
- For ANY content size at or below 50 MB, _check_size_limit MUST NOT raise.
- For ANY export format where generated content exceeds 50 MB, the export() method
  MUST raise without producing a file on disk.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError
from backend.models.diagram import DiagramData, DiagramNode
from backend.models.export import ExportFormat
from backend.services.export_service import ExportService, _MAX_EXPORT_SIZE_BYTES


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Content sizes that exceed the 50 MB limit (up to ~51 MB to avoid memory issues)
oversized_content_strategy = st.integers(
    min_value=_MAX_EXPORT_SIZE_BYTES + 1,
    max_value=_MAX_EXPORT_SIZE_BYTES + 1024 * 1024,  # up to 51 MB
)

# Content sizes at or below the 50 MB limit (test near the boundary)
valid_content_strategy = st.integers(
    min_value=0,
    max_value=_MAX_EXPORT_SIZE_BYTES,
)

# All supported export formats
export_format_strategy = st.sampled_from([ExportFormat.PDF, ExportFormat.PNG, ExportFormat.SVG])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_diagram_data() -> DiagramData:
    """Create a minimal DiagramData fixture for tests."""
    return DiagramData(
        nodes=[
            DiagramNode(
                id="arn:aws:ec2:us-east-1:123456789012:instance/i-test",
                resource_type="ec2",
                name="test-instance",
                region="us-east-1",
                icon_url="/api/images/icons/ec2",
            )
        ],
        edges=[],
        account_id="123456789012",
        scan_timestamp="2024-01-15T10:30:00Z",
        total_resources=1,
        scanned_regions=["us-east-1"],
    )


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestExportSizeLimitEnforcement:
    """Property 26: Export size limit enforcement."""

    @given(size=oversized_content_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_check_size_limit_rejects_oversized_content(self, size: int) -> None:
        """For ANY content size > 50 MB, _check_size_limit MUST raise CloudSpyglassError.

        **Validates: Requirements 11.6**
        """
        service = ExportService()
        content = b"\x00" * size

        with pytest.raises(CloudSpyglassError) as exc_info:
            service._check_size_limit(content)

        assert exc_info.value.error_code == "EXPORT_TOO_LARGE"
        assert exc_info.value.status_code == 413
        assert exc_info.value.recoverable is False

    @given(size=valid_content_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_check_size_limit_accepts_valid_content(self, size: int) -> None:
        """For ANY content size <= 50 MB, _check_size_limit MUST NOT raise.

        **Validates: Requirements 11.6**
        """
        service = ExportService()
        content = b"\x00" * size

        # Should not raise any exception
        service._check_size_limit(content)

    @given(size=oversized_content_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_export_rejects_oversized_without_writing_file(
        self, size: int, fmt: ExportFormat
    ) -> None:
        """For ANY format where generated content exceeds 50 MB, export() MUST raise
        without producing a file on disk.

        **Validates: Requirements 11.6**
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            export_dir = Path(tmp_dir)
            service = ExportService(export_dir=export_dir)
            diagram_data = _make_diagram_data()
            oversized_content = b"\x00" * size

            with patch.object(
                service,
                "_generate_content",
                new=AsyncMock(return_value=oversized_content),
            ):
                with pytest.raises(CloudSpyglassError) as exc_info:
                    await service.export(diagram_data, fmt)

                assert exc_info.value.error_code == "EXPORT_TOO_LARGE"
                assert exc_info.value.status_code == 413
                assert exc_info.value.recoverable is False

            # Verify no file was written to the export directory
            exported_files = list(export_dir.glob("*"))
            assert len(exported_files) == 0, (
                f"No file should be written when content exceeds 50 MB, "
                f"but found: {exported_files}"
            )

    @given(size=oversized_content_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_error_details_contain_size_info(self, size: int) -> None:
        """The error details MUST contain information about the generated size.

        **Validates: Requirements 11.6**
        """
        service = ExportService()
        content = b"\x00" * size

        with pytest.raises(CloudSpyglassError) as exc_info:
            service._check_size_limit(content)

        # Details should mention the size in MB
        assert "MB" in exc_info.value.details
