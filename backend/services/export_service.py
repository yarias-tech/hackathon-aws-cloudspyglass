"""Diagram export to PDF, PNG, and SVG with size limits and timeout."""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from ..exceptions import CloudSpyglassError
from ..models.diagram import DiagramData
from ..models.export import ExportFormat, ExportResult
from ..models.filters import FilterCriteria

logger = logging.getLogger(__name__)

# Default export output directory (mounted volume inside Docker)
_DEFAULT_EXPORT_DIR = Path("/workspace/exports")

# Maximum export file size: 50 MB
_MAX_EXPORT_SIZE_BYTES = 50 * 1024 * 1024

# Export timeout in seconds
_EXPORT_TIMEOUT_SECONDS = 30

# SVG layout constants
_SVG_NODE_WIDTH = 180
_SVG_NODE_HEIGHT = 60
_SVG_NODE_PADDING = 30
_SVG_COLUMNS = 4
_SVG_HEADER_HEIGHT = 80
_SVG_FOOTER_HEIGHT = 60
_PNG_DPI = 300


class ExportService:
    """Diagram export to PDF, PNG, and SVG with size limits."""

    def __init__(self, export_dir: Path | None = None) -> None:
        self._export_dir = export_dir or _DEFAULT_EXPORT_DIR

    async def export(
        self,
        diagram_data: DiagramData,
        format: ExportFormat,
        filters: FilterCriteria | None = None,
    ) -> ExportResult:
        """Export diagram data to the specified format.

        Generates the export file using atomic writes and enforces a 30-second
        timeout and 50 MB size limit.

        Args:
            diagram_data: The diagram payload to render.
            format: Target export format (PDF, PNG, SVG).
            filters: Optional active filter criteria to annotate in the export.

        Returns:
            ExportResult with filename, format, size, and path.

        Raises:
            CloudSpyglassError: EXPORT_TOO_LARGE if output exceeds 50 MB.
            CloudSpyglassError: EXPORT_TIMEOUT if generation exceeds 30 seconds.
            CloudSpyglassError: EXPORT_FAILED on any rendering error.
        """
        try:
            content = await asyncio.wait_for(
                self._generate_content(diagram_data, format, filters),
                timeout=_EXPORT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Export timed out for account %s format %s",
                diagram_data.account_id,
                format.value,
            )
            raise CloudSpyglassError(
                error_code="EXPORT_TIMEOUT",
                message="Export exceeded 30-second time limit.",
                details=f"Account {diagram_data.account_id}, format {format.value}",
                recoverable=True,
                status_code=504,
            )
        except CloudSpyglassError:
            raise
        except Exception as exc:
            logger.error(
                "Export failed for account %s format %s: %s",
                diagram_data.account_id,
                format.value,
                exc,
            )
            raise CloudSpyglassError(
                error_code="EXPORT_FAILED",
                message="Export generation failed.",
                details=str(exc),
                recoverable=False,
                status_code=500,
            ) from exc

        # Enforce size limit
        self._check_size_limit(content)

        # Write atomically to the export directory
        filename = self._generate_filename(diagram_data.account_id, format)
        file_path = self._write_atomic(filename, content)

        size_bytes = len(content)
        logger.info(
            "Export complete: %s (%d bytes)", filename, size_bytes
        )

        return ExportResult(
            filename=filename,
            format=format,
            size_bytes=size_bytes,
            path=str(file_path),
        )

    def _generate_filename(self, account_id: str, format: ExportFormat) -> str:
        """Generate filename with pattern {Account_ID}_{YYYYMMDD_HHmmss}.{format}.

        Args:
            account_id: AWS account identifier.
            format: Export format determining the file extension.

        Returns:
            Formatted filename string.
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        return f"{account_id}_{timestamp}.{format.value}"

    def _check_size_limit(self, content: bytes) -> None:
        """Reject exports exceeding 50 MB.

        Args:
            content: The rendered export content as bytes.

        Raises:
            CloudSpyglassError: EXPORT_TOO_LARGE if content exceeds limit.
        """
        if len(content) > _MAX_EXPORT_SIZE_BYTES:
            size_mb = len(content) / (1024 * 1024)
            raise CloudSpyglassError(
                error_code="EXPORT_TOO_LARGE",
                message="Export would exceed 50 MB size limit.",
                details=f"Generated size: {size_mb:.2f} MB",
                recoverable=False,
                status_code=413,
            )

    async def _generate_content(
        self,
        diagram_data: DiagramData,
        format: ExportFormat,
        filters: FilterCriteria | None,
    ) -> bytes:
        """Generate export content based on format.

        Args:
            diagram_data: Diagram payload to render.
            format: Target format.
            filters: Optional active filters to annotate.

        Returns:
            Rendered content as bytes.
        """
        if format == ExportFormat.SVG:
            return self._render_svg(diagram_data, filters)
        elif format == ExportFormat.PNG:
            return self._render_png(diagram_data, filters)
        elif format == ExportFormat.PDF:
            return self._render_pdf(diagram_data, filters)
        else:
            raise CloudSpyglassError(
                error_code="EXPORT_FAILED",
                message=f"Unsupported export format: {format.value}",
                recoverable=False,
                status_code=500,
            )

    def _render_svg(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria | None,
    ) -> bytes:
        """Render diagram data as SVG XML.

        Generates nodes as labeled rectangles arranged in a grid layout,
        and edges as lines connecting source to target nodes.

        Args:
            diagram_data: Diagram payload to render.
            filters: Optional active filters to annotate.

        Returns:
            SVG content as UTF-8 bytes.
        """
        nodes = diagram_data.nodes
        edges = diagram_data.edges

        # Calculate layout dimensions
        num_nodes = len(nodes)
        rows = (num_nodes + _SVG_COLUMNS - 1) // _SVG_COLUMNS if num_nodes > 0 else 1
        content_width = _SVG_COLUMNS * (_SVG_NODE_WIDTH + _SVG_NODE_PADDING) + _SVG_NODE_PADDING
        content_height = (
            _SVG_HEADER_HEIGHT
            + rows * (_SVG_NODE_HEIGHT + _SVG_NODE_PADDING)
            + _SVG_NODE_PADDING
            + _SVG_FOOTER_HEIGHT
        )

        # Build node position map for edge rendering
        node_positions: dict[str, tuple[float, float]] = {}
        for idx, node in enumerate(nodes):
            col = idx % _SVG_COLUMNS
            row = idx // _SVG_COLUMNS
            x = _SVG_NODE_PADDING + col * (_SVG_NODE_WIDTH + _SVG_NODE_PADDING)
            y = _SVG_HEADER_HEIGHT + _SVG_NODE_PADDING + row * (_SVG_NODE_HEIGHT + _SVG_NODE_PADDING)
            node_positions[node.id] = (
                x + _SVG_NODE_WIDTH / 2,
                y + _SVG_NODE_HEIGHT / 2,
            )

        # Build SVG elements
        svg_parts: list[str] = []
        svg_parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{content_width}" height="{content_height}" '
            f'viewBox="0 0 {content_width} {content_height}">'
        )

        # Background
        svg_parts.append(
            f'<rect width="{content_width}" height="{content_height}" fill="#ffffff"/>'
        )

        # Header with account info
        header_text = (
            f"Account: {xml_escape(diagram_data.account_id)} | "
            f"Scanned: {xml_escape(diagram_data.scan_timestamp)} | "
            f"Resources: {diagram_data.total_resources}"
        )
        svg_parts.append(
            f'<text x="{_SVG_NODE_PADDING}" y="30" '
            f'font-family="Arial, sans-serif" font-size="14" fill="#333333">'
            f'{header_text}</text>'
        )

        # Filter annotation in header area when filters are active
        if filters and (filters.tag_filters or filters.type_filters):
            filter_text = self._format_filter_annotation(filters)
            svg_parts.append(
                f'<text x="{_SVG_NODE_PADDING}" y="55" '
                f'font-family="Arial, sans-serif" font-size="11" fill="#666666">'
                f'Filters: {xml_escape(filter_text)}</text>'
            )

        # Edge colors by category
        edge_colors = {
            "network": "#2196F3",
            "iam": "#FF9800",
            "event": "#9C27B0",
            "data": "#4CAF50",
        }

        # Render edges as lines
        for edge in edges:
            if edge.source in node_positions and edge.target in node_positions:
                x1, y1 = node_positions[edge.source]
                x2, y2 = node_positions[edge.target]
                color = edge_colors.get(edge.category, "#999999")
                svg_parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="{color}" stroke-width="1.5" opacity="0.6"/>'
                )

        # Render nodes as rectangles with labels
        for idx, node in enumerate(nodes):
            col = idx % _SVG_COLUMNS
            row = idx // _SVG_COLUMNS
            x = _SVG_NODE_PADDING + col * (_SVG_NODE_WIDTH + _SVG_NODE_PADDING)
            y = _SVG_HEADER_HEIGHT + _SVG_NODE_PADDING + row * (_SVG_NODE_HEIGHT + _SVG_NODE_PADDING)

            # Node rectangle — color by service type
            if node.is_external:
                fill_color = "#FFF3E0"
                stroke_color = "#E65100"
            else:
                fill_color, stroke_color = self._get_service_colors(node.resource_type)

            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{_SVG_NODE_WIDTH}" '
                f'height="{_SVG_NODE_HEIGHT}" rx="4" ry="4" '
                f'fill="{fill_color}" stroke="{stroke_color}" stroke-width="1.5"/>'
            )

            # Node type label — use textLength to guarantee fit
            type_text = xml_escape(node.resource_type)
            text_max_width = _SVG_NODE_WIDTH - 20
            svg_parts.append(
                f'<text x="{x + 10}" y="{y + 20}" '
                f'font-family="Arial, sans-serif" font-size="10" '
                f'textLength="{min(len(node.resource_type) * 6, text_max_width)}" '
                f'lengthAdjust="spacingAndGlyphs" '
                f'fill="#666666">{type_text}</text>'
            )

            # Node name label — use textLength to guarantee fit
            name_text = xml_escape(node.name)
            svg_parts.append(
                f'<text x="{x + 10}" y="{y + 42}" '
                f'font-family="Arial, sans-serif" font-size="11" '
                f'font-weight="bold" '
                f'textLength="{min(len(node.name) * 6.5, text_max_width)}" '
                f'lengthAdjust="spacingAndGlyphs" '
                f'fill="#333333">{name_text}</text>'
            )

        # Footer with regions
        footer_y = content_height - _SVG_FOOTER_HEIGHT + 20
        regions_text = f"Regions: {', '.join(diagram_data.scanned_regions)}"
        svg_parts.append(
            f'<text x="{_SVG_NODE_PADDING}" y="{footer_y}" '
            f'font-family="Arial, sans-serif" font-size="10" fill="#999999">'
            f'{xml_escape(regions_text)}</text>'
        )

        svg_parts.append("</svg>")

        return "\n".join(svg_parts).encode("utf-8")

    def _render_png(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria | None,
    ) -> bytes:
        """Render diagram data as PNG at 300 DPI.

        Converts the SVG representation to PNG using cairosvg at 300 DPI.

        Args:
            diagram_data: Diagram payload to render.
            filters: Optional active filters to annotate.

        Returns:
            PNG content as bytes.
        """
        import cairosvg

        # Generate SVG first as the source representation
        svg_content = self._render_svg(diagram_data, filters)

        # Convert SVG to PNG at 300 DPI (scale factor = 300/96 ≈ 3.125)
        scale = _PNG_DPI / 96
        png_content = cairosvg.svg2png(
            bytestring=svg_content,
            scale=scale,
        )

        return png_content

    def _render_pdf(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria | None,
    ) -> bytes:
        """Render diagram data as PDF.

        Converts the SVG representation to a vector PDF using cairosvg.

        Args:
            diagram_data: Diagram payload to render.
            filters: Optional active filters to annotate.

        Returns:
            PDF content as bytes.
        """
        import cairosvg

        # Generate SVG first as the source representation
        svg_content = self._render_svg(diagram_data, filters)

        # Convert SVG to PDF (vector, preserving quality)
        pdf_content = cairosvg.svg2pdf(bytestring=svg_content)

        return pdf_content

    def _format_filter_annotation(self, filters: FilterCriteria) -> str:
        """Format active filter criteria as a text annotation.

        Args:
            filters: Active filter criteria.

        Returns:
            Human-readable filter description string.
        """
        parts: list[str] = []

        if filters.tag_filters:
            tag_strs = [f"{tf.key}={tf.value}" for tf in filters.tag_filters]
            parts.append(f"Tags: {', '.join(tag_strs)}")

        if filters.type_filters:
            parts.append(f"Types: {', '.join(filters.type_filters)}")

        return " | ".join(parts)

    @staticmethod
    def _get_service_colors(resource_type: str) -> tuple[str, str]:
        """Return (fill_color, stroke_color) for a given AWS resource type.

        Each service category gets a distinct color palette for visual
        differentiation in exported diagrams.

        Args:
            resource_type: The AWS resource type string (e.g. "EC2", "Lambda").

        Returns:
            Tuple of (fill_color, stroke_color) as hex strings.
        """
        # Color palette per AWS service type (fill, stroke)
        service_colors: dict[str, tuple[str, str]] = {
            # Compute — orange
            "EC2": ("#FFF3E0", "#E65100"),
            "Lambda": ("#F3E5F5", "#6A1B9A"),
            "ECS": ("#FFF3E0", "#E65100"),
            "EKS": ("#FFF3E0", "#BF360C"),
            # Networking — blue
            "VPC": ("#E3F2FD", "#1565C0"),
            "Subnet": ("#E3F2FD", "#1976D2"),
            "SecurityGroup": ("#E8EAF6", "#283593"),
            "ELB": ("#E3F2FD", "#0D47A1"),
            "ALB": ("#E3F2FD", "#0D47A1"),
            "NLB": ("#E3F2FD", "#0D47A1"),
            "CloudFront": ("#E3F2FD", "#01579B"),
            "Route53": ("#E3F2FD", "#01579B"),
            "APIGateway": ("#E3F2FD", "#1A237E"),
            # Storage — green
            "S3": ("#E8F5E9", "#2E7D32"),
            "EBS": ("#E8F5E9", "#1B5E20"),
            "EFS": ("#E8F5E9", "#388E3C"),
            # Database — purple
            "RDS": ("#EDE7F6", "#4527A0"),
            "DynamoDB": ("#EDE7F6", "#311B92"),
            "ElastiCache": ("#EDE7F6", "#6A1B9A"),
            # Messaging — pink
            "SNS": ("#FCE4EC", "#880E4F"),
            "SQS": ("#FCE4EC", "#AD1457"),
            "EventBridge": ("#FCE4EC", "#C2185B"),
            # Identity — yellow
            "IAM": ("#FFFDE7", "#F57F17"),
            "IAMRole": ("#FFFDE7", "#F57F17"),
            "IAMPolicy": ("#FFFDE7", "#FF8F00"),
            # Monitoring — teal
            "CloudWatch": ("#E0F2F1", "#00695C"),
            "CloudTrail": ("#E0F2F1", "#004D40"),
        }

        # Try exact match first
        if resource_type in service_colors:
            return service_colors[resource_type]

        # Try partial match (resource_type might be prefixed, e.g. "AWS::EC2::Instance")
        resource_upper = resource_type.upper()
        for key, colors in service_colors.items():
            if key.upper() in resource_upper:
                return colors

        # Default — neutral grey
        return ("#F5F5F5", "#616161")

    def _write_atomic(self, filename: str, content: bytes) -> Path:
        """Write content to export directory using atomic write pattern.

        Writes to a temp file first, then atomically replaces the target
        to prevent partial or corrupted files.

        Args:
            filename: Target filename.
            content: File content as bytes.

        Returns:
            Path to the written file.

        Raises:
            CloudSpyglassError: EXPORT_FAILED if write fails.
        """
        self._ensure_export_dir()
        target_path = self._export_dir / filename

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._export_dir),
                prefix=f".export_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "wb") as tmp_file:
                    tmp_file.write(content)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())

                # Atomic replace
                os.replace(tmp_path, str(target_path))
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except CloudSpyglassError:
            raise
        except Exception as exc:
            logger.error("Failed to write export file %s: %s", filename, exc)
            raise CloudSpyglassError(
                error_code="EXPORT_FAILED",
                message="Failed to write export file to disk.",
                details=str(exc),
                recoverable=True,
                status_code=500,
            ) from exc

        return target_path

    def _ensure_export_dir(self) -> None:
        """Create the export directory if it does not exist."""
        self._export_dir.mkdir(parents=True, exist_ok=True)
