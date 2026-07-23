"""API routes for diagram export operations."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..dependencies import export_service, filter_engine
from ..exceptions import CloudSpyglassError
from ..models.export import ExportRequest, ExportResult
from .scan import get_last_scan_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])

# Content-type mapping for export formats
_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "svg": "image/svg+xml",
}

# Pattern to validate export filenames (account_id_timestamp.format)
_FILENAME_PATTERN = re.compile(r"^[\w\-]+_\d{8}_\d{6}\.(pdf|png|svg)$")


@router.post("", response_model=ExportResult)
async def trigger_export(request: ExportRequest) -> ExportResult:
    """Export the current diagram view in the requested format.

    Accepts an ExportRequest with format and optional filters.
    Uses the latest scan data to generate the export.

    Requirements: 11.4
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    # Convert scan result to diagram data, applying filters if provided
    tag_filters = request.filters.tag_filters if request.filters else None
    type_filters = request.filters.type_filters if request.filters else None
    tag_filter_operator = request.filters.tag_filter_operator if request.filters else "AND"

    filtered_result = filter_engine.apply_filters(
        scan_result,
        tag_filters=tag_filters if tag_filters else None,
        type_filters=type_filters if type_filters else None,
        tag_filter_operator=tag_filter_operator,
    )

    # Export the diagram data
    result = await export_service.export(
        diagram_data=filtered_result.diagram,
        format=request.format,
        filters=request.filters,
    )

    return result


@router.get("/download/{filename}")
async def download_export(filename: str) -> FileResponse:
    """Download a previously generated export file.

    Serves the file with appropriate Content-Disposition and Content-Type
    headers so the browser triggers a download.

    Requirements: 11.4
    """
    # Validate filename to prevent path traversal
    if not _FILENAME_PATTERN.match(filename):
        raise CloudSpyglassError(
            error_code="INVALID_FILENAME",
            message="Invalid export filename.",
            recoverable=False,
            status_code=400,
        )

    file_path = Path(export_service._export_dir) / filename

    if not file_path.is_file():
        raise CloudSpyglassError(
            error_code="EXPORT_NOT_FOUND",
            message=f"Export file '{filename}' not found.",
            recoverable=True,
            status_code=404,
        )

    # Determine content type from file extension
    extension = filename.rsplit(".", 1)[-1]
    content_type = _CONTENT_TYPES.get(extension, "application/octet-stream")

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
