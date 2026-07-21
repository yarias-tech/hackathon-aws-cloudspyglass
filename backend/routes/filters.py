"""API routes for tag autocomplete suggestions."""

from fastapi import APIRouter, Query

from ..exceptions import CloudSpyglassError
from ..models.filters import TagSuggestion
from ..services.filter_engine import FilterEngine
from .scan import get_last_scan_result

router = APIRouter(prefix="/api/tags", tags=["filters"])

_filter_engine = FilterEngine()


@router.get("/suggestions", response_model=list[TagSuggestion])
async def get_tag_suggestions(
    prefix: str = Query(default="", max_length=128),
) -> list[TagSuggestion]:
    """Return tag autocomplete suggestions filtered by prefix.

    Returns up to 20 tag key-value pairs ordered by descending frequency.
    The prefix matches case-insensitively against either the tag key or value.

    Requirements: 7.2
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    return _filter_engine.get_tag_suggestions(scan_result, prefix)
