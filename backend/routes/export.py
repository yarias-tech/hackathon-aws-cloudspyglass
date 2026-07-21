"""API routes for diagram export operations."""

import logging

from fastapi import APIRouter

from ..exceptions import CloudSpyglassError
from ..models.export import ExportRequest, ExportResult
from ..services.export_service import ExportService
from ..services.filter_engine import FilterEngine
from .scan import get_last_scan_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])

_export_service = ExportService()
_filter_engine = FilterEngine()


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

    filtered_result = _filter_engine.apply_filters(
        scan_result,
        tag_filters=tag_filters if tag_filters else None,
        type_filters=type_filters if type_filters else None,
    )

    # Export the diagram data
    result = await _export_service.export(
        diagram_data=filtered_result.diagram,
        format=request.format,
        filters=request.filters,
    )

    return result
