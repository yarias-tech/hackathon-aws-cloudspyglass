"""API routes for diagram data retrieval and filtered views."""

import json
import logging
from urllib.parse import unquote

from fastapi import APIRouter, Query

from ..dependencies import filter_engine
from ..exceptions import CloudSpyglassError
from ..models.diagram import DiagramData
from ..models.filters import FilteredResult, TagFilter
from ..models.resources import Resource
from .scan import get_last_scan_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["diagrams"])


@router.get("/diagrams/latest", response_model=DiagramData)
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
    result = filter_engine.apply_filters(scan_result)
    return result.diagram


@router.get("/diagrams/latest/filtered", response_model=FilteredResult)
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

    # Parse type_filters from JSON array or comma-separated string
    parsed_type_filters: list[str] = []
    if type_filters:
        # Try JSON array first (frontend sends ["type1","type2"])
        try:
            raw_types = json.loads(type_filters)
            if isinstance(raw_types, list):
                parsed_type_filters = [str(t).strip() for t in raw_types if str(t).strip()]
            else:
                # Not a list, treat as comma-separated
                parsed_type_filters = [t.strip() for t in type_filters.split(",") if t.strip()]
        except (json.JSONDecodeError, ValueError):
            # Fall back to comma-separated
            parsed_type_filters = [t.strip() for t in type_filters.split(",") if t.strip()]

    return filter_engine.apply_filters(
        scan_result,
        tag_filters=parsed_tag_filters if parsed_tag_filters else None,
        type_filters=parsed_type_filters if parsed_type_filters else None,
    )


@router.get("/resources/{resource_id:path}", response_model=Resource)
async def get_resource_detail(resource_id: str) -> Resource:
    """Return full resource metadata for a given resource ARN.

    Looks up the resource from the latest scan result.
    The resource_id is the ARN (URL-encoded in the path).
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    decoded_id = unquote(resource_id)
    for resource in scan_result.resources:
        if resource.arn == decoded_id:
            return resource

    raise CloudSpyglassError(
        error_code="RESOURCE_NOT_FOUND",
        message=f"Resource not found: {decoded_id}",
        recoverable=False,
        status_code=404,
    )
