"""API routes for diagram data retrieval and filtered views."""

import json
import logging

from fastapi import APIRouter, Query

from ..exceptions import CloudSpyglassError
from ..models.diagram import DiagramData
from ..models.filters import FilteredResult, TagFilter
from ..services.filter_engine import FilterEngine
from .scan import get_last_scan_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagrams", tags=["diagrams"])

_filter_engine = FilterEngine()


@router.get("/latest", response_model=DiagramData)
async def get_latest_diagram() -> DiagramData:
    """Return the latest unfiltered diagram data from the most recent scan.

    Requirements: 5.1
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    # Apply no filters to get full diagram
    result = _filter_engine.apply_filters(scan_result)
    return result.diagram


@router.get("/latest/filtered", response_model=FilteredResult)
async def get_filtered_diagram(
    tag_filters: str | None = Query(
        default=None,
        description='JSON array of tag filters, e.g. [{"key":"env","value":"prod"}]',
    ),
    type_filters: str | None = Query(
        default=None,
        description="Comma-separated list of resource types to include",
    ),
) -> FilteredResult:
    """Return filtered diagram data based on tag and/or type criteria.

    Accepts FilterCriteria as query params:
    - tag_filters: JSON string of [{key, value}] objects (AND logic)
    - type_filters: Comma-separated resource type strings (OR logic)

    Requirements: 7.2, 5.1
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    # Parse tag_filters from JSON string
    parsed_tag_filters: list[TagFilter] = []
    if tag_filters:
        try:
            raw_tags = json.loads(tag_filters)
            if not isinstance(raw_tags, list):
                raise CloudSpyglassError(
                    error_code="INVALID_FILTER",
                    message="tag_filters must be a JSON array.",
                    recoverable=False,
                    status_code=400,
                )
            parsed_tag_filters = [TagFilter(**item) for item in raw_tags]
        except json.JSONDecodeError:
            raise CloudSpyglassError(
                error_code="INVALID_FILTER",
                message="tag_filters is not valid JSON.",
                recoverable=False,
                status_code=400,
            )
        except (TypeError, ValueError) as exc:
            raise CloudSpyglassError(
                error_code="INVALID_FILTER",
                message=f"Invalid tag filter format: {exc}",
                recoverable=False,
                status_code=400,
            )

    # Parse type_filters from comma-separated string
    parsed_type_filters: list[str] = []
    if type_filters:
        parsed_type_filters = [t.strip() for t in type_filters.split(",") if t.strip()]

    return _filter_engine.apply_filters(
        scan_result,
        tag_filters=parsed_tag_filters if parsed_tag_filters else None,
        type_filters=parsed_type_filters if parsed_type_filters else None,
    )
