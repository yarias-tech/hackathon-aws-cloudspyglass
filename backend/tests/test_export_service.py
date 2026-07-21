"""Unit tests for the ExportService."""

import asyncio
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.exceptions import CloudSpyglassError
from backend.models.diagram import DiagramData, DiagramEdge, DiagramNode
from backend.models.export import ExportFormat
from backend.models.filters import FilterCriteria, TagFilter
from backend.services.export_service import ExportService


@pytest.fixture
def tmp_export_dir(tmp_path: Path) -> Path:
    """Create a temporary export directory for testing."""
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    return export_dir


@pytest.fixture
def export_service(tmp_export_dir: Path) -> ExportService:
    """Create an ExportService instance with a temporary directory."""
    return ExportService(export_dir=tmp_export_dir)


@pytest.fixture
def sample_diagram_data() -> DiagramData:
    """Create a minimal valid DiagramData for testing."""
    return DiagramData(
        nodes=[
            DiagramNode(
                id="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
                resource_type="ec2",
                name="my-instance",
                region="us-east-1",
                icon_url="/api/images/icons/ec2",
            ),
            DiagramNode(
                id="arn:aws:s3:::my-bucket",
                resource_type="s3",
                name="my-bucket",
                region="us-east-1",
                icon_url="/api/images/icons/s3",
            ),
        ],
        edges=[
            DiagramEdge(
                id="edge-1",
                source="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
                target="arn:aws:s3:::my-bucket",
                category="data",
                derived_from="BucketPolicy",
                label="read/write",
            ),
        ],
        account_id="123456789012",
        scan_timestamp="2024-01-15T10:30:00Z",
        total_resources=2,
        scanned_regions=["us-east-1"],
    )


@pytest.fixture
def sample_filters() -> FilterCriteria:
    """Create sample filter criteria for testing."""
    return FilterCriteria(
        tag_filters=[TagFilter(key="Environment", value="prod")],
        type_filters=["ec2", "s3"],
    )


@pytest.fixture
def empty_diagram_data() -> DiagramData:
    """Create an empty DiagramData for edge case testing."""
    return DiagramData(
        nodes=[],
        edges=[],
        account_id="999888777666",
        scan_timestamp="2024-06-01T00:00:00Z",
        total_resources=0,
        scanned_regions=["us-west-2"],
    )


class TestExport:
    """Tests for the export() method."""

    async def test_export_svg_produces_file(
        self, export_service: ExportService, sample_diagram_data: DiagramData, tmp_export_dir: Path
    ) -> None:
        """Export SVG creates a file in the export directory."""
        result = await export_service.export(sample_diagram_data, ExportFormat.SVG)

        file_path = Path(result.path)
        assert file_path.exists()
        assert result.format == ExportFormat.SVG
        assert result.size_bytes > 0
        assert result.filename.endswith(".svg")

    async def test_export_png_produces_file(
        self, export_service: ExportService, sample_diagram_data: DiagramData, tmp_export_dir: Path
    ) -> None:
        """Export PNG creates a valid PNG file."""
        result = await export_service.export(sample_diagram_data, ExportFormat.PNG)

        file_path = Path(result.path)
        assert file_path.exists()
        assert result.format == ExportFormat.PNG
        assert result.size_bytes > 0
        assert result.filename.endswith(".png")

        # Verify PNG signature
        content = file_path.read_bytes()
        assert content[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_export_pdf_produces_file(
        self, export_service: ExportService, sample_diagram_data: DiagramData, tmp_export_dir: Path
    ) -> None:
        """Export PDF creates a valid PDF file."""
        result = await export_service.export(sample_diagram_data, ExportFormat.PDF)

        file_path = Path(result.path)
        assert file_path.exists()
        assert result.format == ExportFormat.PDF
        assert result.size_bytes > 0
        assert result.filename.endswith(".pdf")

        # Verify PDF header
        content = file_path.read_bytes()
        assert content.startswith(b"%PDF-1.4")

    async def test_export_svg_contains_diagram_content(
        self, export_service: ExportService, sample_diagram_data: DiagramData
    ) -> None:
        """SVG export includes node and edge representations."""
        result = await export_service.export(sample_diagram_data, ExportFormat.SVG)

        content = Path(result.path).read_text(encoding="utf-8")
        assert "<svg" in content
        assert "my-instance" in content
        assert "my-bucket" in content
        assert "123456789012" in content

    async def test_export_with_filters_includes_annotation(
        self,
        export_service: ExportService,
        sample_diagram_data: DiagramData,
        sample_filters: FilterCriteria,
    ) -> None:
        """Export with active filters includes filter annotation."""
        result = await export_service.export(
            sample_diagram_data, ExportFormat.SVG, filters=sample_filters
        )

        content = Path(result.path).read_text(encoding="utf-8")
        assert "Environment=prod" in content
        assert "ec2" in content
        assert "s3" in content

    async def test_export_without_filters_no_filter_annotation(
        self, export_service: ExportService, sample_diagram_data: DiagramData
    ) -> None:
        """Export without filters does not include filter annotation line."""
        result = await export_service.export(sample_diagram_data, ExportFormat.SVG)

        content = Path(result.path).read_text(encoding="utf-8")
        assert "Filters:" not in content

    async def test_export_empty_diagram(
        self, export_service: ExportService, empty_diagram_data: DiagramData
    ) -> None:
        """Export handles empty diagram data without error."""
        result = await export_service.export(empty_diagram_data, ExportFormat.SVG)

        assert result.size_bytes > 0
        content = Path(result.path).read_text(encoding="utf-8")
        assert "<svg" in content
        assert "999888777666" in content

    async def test_export_creates_directory_if_missing(
        self, tmp_path: Path, sample_diagram_data: DiagramData
    ) -> None:
        """Export creates the export directory if it does not exist."""
        export_dir = tmp_path / "nonexistent" / "exports"
        service = ExportService(export_dir=export_dir)

        result = await service.export(sample_diagram_data, ExportFormat.SVG)
        assert Path(result.path).exists()


class TestExportSizeLimit:
    """Tests for the 50 MB size limit enforcement."""

    async def test_rejects_export_exceeding_50mb(
        self, export_service: ExportService, sample_diagram_data: DiagramData
    ) -> None:
        """Export raises EXPORT_TOO_LARGE for oversized content."""
        # Create content larger than 50 MB by patching _render_svg
        large_content = b"x" * (50 * 1024 * 1024 + 1)

        with patch.object(export_service, "_render_svg", return_value=large_content):
            with pytest.raises(CloudSpyglassError) as exc_info:
                await export_service.export(sample_diagram_data, ExportFormat.SVG)

        assert exc_info.value.error_code == "EXPORT_TOO_LARGE"
        assert exc_info.value.status_code == 413
        assert exc_info.value.recoverable is False

    def test_check_size_limit_passes_under_limit(self, export_service: ExportService) -> None:
        """_check_size_limit does not raise for content under 50 MB."""
        content = b"x" * (49 * 1024 * 1024)
        # Should not raise
        export_service._check_size_limit(content)

    def test_check_size_limit_raises_over_limit(self, export_service: ExportService) -> None:
        """_check_size_limit raises for content over 50 MB."""
        content = b"x" * (50 * 1024 * 1024 + 1)

        with pytest.raises(CloudSpyglassError) as exc_info:
            export_service._check_size_limit(content)

        assert exc_info.value.error_code == "EXPORT_TOO_LARGE"
        assert exc_info.value.status_code == 413


class TestExportTimeout:
    """Tests for the 30-second export timeout."""

    async def test_timeout_raises_export_timeout(
        self, export_service: ExportService, sample_diagram_data: DiagramData
    ) -> None:
        """Export raises EXPORT_TIMEOUT when generation exceeds 30 seconds."""

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(60)
            return b""

        with patch.object(export_service, "_generate_content", side_effect=slow_generate):
            with pytest.raises(CloudSpyglassError) as exc_info:
                await export_service.export(sample_diagram_data, ExportFormat.SVG)

        assert exc_info.value.error_code == "EXPORT_TIMEOUT"
        assert exc_info.value.status_code == 504
        assert exc_info.value.recoverable is True


class TestGenerateFilename:
    """Tests for the _generate_filename() method."""

    def test_filename_format_pattern(self, export_service: ExportService) -> None:
        """Filename follows {Account_ID}_{YYYYMMDD_HHmmss}.{format} pattern."""
        filename = export_service._generate_filename("123456789012", ExportFormat.SVG)

        # Pattern: 123456789012_YYYYMMDD_HHmmss.svg
        pattern = r"^123456789012_\d{8}_\d{6}\.svg$"
        assert re.match(pattern, filename), f"Filename '{filename}' doesn't match expected pattern"

    def test_filename_uses_correct_extension_pdf(self, export_service: ExportService) -> None:
        """Filename uses .pdf extension for PDF format."""
        filename = export_service._generate_filename("111111111111", ExportFormat.PDF)
        assert filename.endswith(".pdf")

    def test_filename_uses_correct_extension_png(self, export_service: ExportService) -> None:
        """Filename uses .png extension for PNG format."""
        filename = export_service._generate_filename("222222222222", ExportFormat.PNG)
        assert filename.endswith(".png")

    def test_filename_uses_correct_extension_svg(self, export_service: ExportService) -> None:
        """Filename uses .svg extension for SVG format."""
        filename = export_service._generate_filename("333333333333", ExportFormat.SVG)
        assert filename.endswith(".svg")

    def test_filename_starts_with_account_id(self, export_service: ExportService) -> None:
        """Filename starts with the account_id."""
        filename = export_service._generate_filename("987654321098", ExportFormat.SVG)
        assert filename.startswith("987654321098_")

    def test_filename_timestamp_is_utc(self, export_service: ExportService) -> None:
        """Filename timestamp uses UTC time."""
        from datetime import datetime, timezone

        before = datetime.now(timezone.utc).replace(microsecond=0)
        filename = export_service._generate_filename("123456789012", ExportFormat.SVG)
        after = datetime.now(timezone.utc).replace(microsecond=0)

        # Extract timestamp from filename
        ts_str = filename.split("_", 1)[1].rsplit(".", 1)[0]  # YYYYMMDD_HHmmss
        ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)

        assert before <= ts <= after


class TestExportError:
    """Tests for export error handling."""

    async def test_rendering_error_raises_export_failed(
        self, export_service: ExportService, sample_diagram_data: DiagramData
    ) -> None:
        """Rendering exceptions produce EXPORT_FAILED error."""

        async def failing_generate(*args, **kwargs):
            raise RuntimeError("Rendering engine crashed")

        with patch.object(export_service, "_generate_content", side_effect=failing_generate):
            with pytest.raises(CloudSpyglassError) as exc_info:
                await export_service.export(sample_diagram_data, ExportFormat.SVG)

        assert exc_info.value.error_code == "EXPORT_FAILED"
        assert exc_info.value.status_code == 500

    async def test_no_partial_file_on_failure(
        self, export_service: ExportService, sample_diagram_data: DiagramData, tmp_export_dir: Path
    ) -> None:
        """Failed export does not leave partial or temp files."""

        async def failing_generate(*args, **kwargs):
            raise RuntimeError("Render failed")

        with patch.object(export_service, "_generate_content", side_effect=failing_generate):
            with pytest.raises(CloudSpyglassError):
                await export_service.export(sample_diagram_data, ExportFormat.SVG)

        # No files should remain in the export directory
        files = list(tmp_export_dir.iterdir())
        assert len(files) == 0


class TestFilterAnnotation:
    """Tests for filter annotation formatting."""

    def test_format_tag_filters(self, export_service: ExportService) -> None:
        """Tag filters are formatted as key=value pairs."""
        filters = FilterCriteria(
            tag_filters=[
                TagFilter(key="Env", value="prod"),
                TagFilter(key="Team", value="backend"),
            ]
        )
        annotation = export_service._format_filter_annotation(filters)
        assert "Env=prod" in annotation
        assert "Team=backend" in annotation

    def test_format_type_filters(self, export_service: ExportService) -> None:
        """Type filters are included in the annotation."""
        filters = FilterCriteria(type_filters=["ec2", "lambda"])
        annotation = export_service._format_filter_annotation(filters)
        assert "ec2" in annotation
        assert "lambda" in annotation

    def test_format_combined_filters(self, export_service: ExportService) -> None:
        """Both tag and type filters are formatted together."""
        filters = FilterCriteria(
            tag_filters=[TagFilter(key="Env", value="prod")],
            type_filters=["s3"],
        )
        annotation = export_service._format_filter_annotation(filters)
        assert "Env=prod" in annotation
        assert "s3" in annotation
