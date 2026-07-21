"""API routes for triggering and monitoring infrastructure scans."""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from ..exceptions import CloudSpyglassError
from ..models.scan import ScanRequest, ScanResult
from ..services.credential_manager import CredentialManager
from ..services.scanner import Scanner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])


# ---------------------------------------------------------------------------
# Scan state tracking
# ---------------------------------------------------------------------------


class ScanStatus(str, Enum):
    """Possible states of the scan lifecycle."""

    idle = "idle"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class ScanProgress(BaseModel):
    """Response model for GET /api/scan/status."""

    status: ScanStatus
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    total_resources: int | None = None
    total_regions: int | None = None
    total_failures: int | None = None


# Module-level singletons (matching pattern from credentials.py)
_credential_manager = CredentialManager()
_scanner = Scanner(_credential_manager)

# Module-level scan state
_scan_status: ScanStatus = ScanStatus.idle
_scan_started_at: str | None = None
_scan_completed_at: str | None = None
_scan_error_message: str | None = None
_last_scan_result: ScanResult | None = None


# ---------------------------------------------------------------------------
# Background scan task
# ---------------------------------------------------------------------------


async def _run_scan(regions: list[str] | None) -> None:
    """Execute the scan in the background, updating module-level state."""
    global _scan_status, _scan_started_at, _scan_completed_at
    global _scan_error_message, _last_scan_result

    try:
        result = await _scanner.scan(regions=regions)
        _last_scan_result = result
        _scan_status = ScanStatus.completed
        _scan_completed_at = datetime.now(timezone.utc).isoformat()
        _scan_error_message = None
        logger.info(
            "Scan completed: %d resources across %d regions",
            len(result.resources),
            len(result.scanned_regions),
        )
    except Exception as exc:
        _scan_status = ScanStatus.failed
        _scan_completed_at = datetime.now(timezone.utc).isoformat()
        _scan_error_message = str(exc)
        logger.exception("Scan failed: %s", exc)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("")
async def trigger_scan(request: ScanRequest) -> dict[str, Any]:
    """Trigger a new infrastructure scan.

    Rejects the request if a scan is already in progress (409 Conflict).

    Requirements: 3.1, 3.2
    """
    global _scan_status, _scan_started_at, _scan_completed_at, _scan_error_message

    if _scan_status == ScanStatus.in_progress:
        raise CloudSpyglassError(
            error_code="SCAN_IN_PROGRESS",
            message="A scan is already in progress. Please wait for it to complete.",
            details=f"Scan started at {_scan_started_at}",
            recoverable=False,
            status_code=409,
        )

    # Transition to in_progress
    _scan_status = ScanStatus.in_progress
    _scan_started_at = datetime.now(timezone.utc).isoformat()
    _scan_completed_at = None
    _scan_error_message = None

    # Launch scan as a background coroutine
    asyncio.create_task(_run_scan(request.regions))

    return {
        "status": "accepted",
        "message": "Scan initiated",
        "started_at": _scan_started_at,
        "regions": request.regions,
    }


@router.get("/status", response_model=ScanProgress)
async def get_scan_status() -> ScanProgress:
    """Return the current scan progress/status.

    Requirements: 3.1, 3.2
    """
    progress = ScanProgress(
        status=_scan_status,
        started_at=_scan_started_at,
        completed_at=_scan_completed_at,
        error_message=_scan_error_message,
    )

    if _last_scan_result is not None:
        progress.total_resources = len(_last_scan_result.resources)
        progress.total_regions = len(_last_scan_result.scanned_regions)
        progress.total_failures = len(_last_scan_result.failures)

    return progress
