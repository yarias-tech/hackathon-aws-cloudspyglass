"""API routes for triggering and monitoring infrastructure scans."""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..dependencies import (
    get_relationship_resolver,
    scan_storage,
    scanner,
)
from ..exceptions import CloudSpyglassError
from ..models.scan import ScanRequest, ScanResult

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


# Module-level scan state
_scan_status: ScanStatus = ScanStatus.idle
_scan_started_at: str | None = None
_scan_completed_at: str | None = None
_scan_error_message: str | None = None
_last_scan_result: ScanResult | None = None
_scan_task: asyncio.Task | None = None
_scan_cancelled: bool = False


# ---------------------------------------------------------------------------
# Background scan task
# ---------------------------------------------------------------------------


async def _run_scan(regions: list[str] | None) -> None:
    """Execute the scan in the background, updating module-level state."""
    global _scan_status, _scan_started_at, _scan_completed_at
    global _scan_error_message, _last_scan_result, _scan_cancelled

    try:
        if _scan_cancelled:
            _scan_status = ScanStatus.idle
            _scan_completed_at = datetime.now(timezone.utc).isoformat()
            _scan_error_message = "Scan cancelled by user"
            return

        result = await scanner.scan(regions=regions)

        if _scan_cancelled:
            _scan_status = ScanStatus.idle
            _scan_completed_at = datetime.now(timezone.utc).isoformat()
            _scan_error_message = "Scan cancelled by user"
            return

        # Resolve relationships using the account_id from the scan result
        account_id = result.account_id
        if account_id and result.resources:
            try:
                resolver = get_relationship_resolver(account_id)
                relationships, unresolved = resolver.resolve(result.resources)
                # Attach relationships and unresolved resources to the scan result
                result.relationships = relationships
                result.resources.extend(unresolved)
            except Exception as rel_exc:
                logger.warning("Relationship resolution failed: %s", rel_exc)

        _last_scan_result = result
        _scan_status = ScanStatus.completed
        _scan_completed_at = datetime.now(timezone.utc).isoformat()
        _scan_error_message = None

        # Persist scan result to storage
        if account_id:
            try:
                await scan_storage.save(account_id, result)
            except Exception as storage_exc:
                logger.warning("Failed to persist scan result: %s", storage_exc)

        logger.info(
            "Scan completed: %d resources across %d regions",
            len(result.resources),
            len(result.scanned_regions),
        )
    except asyncio.CancelledError:
        _scan_status = ScanStatus.idle
        _scan_completed_at = datetime.now(timezone.utc).isoformat()
        _scan_error_message = "Scan cancelled by user"
        logger.info("Scan cancelled by user")
    except Exception as exc:
        _scan_status = ScanStatus.failed
        _scan_completed_at = datetime.now(timezone.utc).isoformat()
        _scan_error_message = str(exc)
        logger.exception("Scan failed: %s", exc)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def get_last_scan_result() -> ScanResult | None:
    """Return the most recent scan result (or None if no scan has completed)."""
    return _last_scan_result


@router.post("")
async def trigger_scan(request: ScanRequest | None = None) -> dict[str, Any]:
    """Trigger a new infrastructure scan.

    Rejects the request if a scan is already in progress (409 Conflict).

    Requirements: 3.1, 3.2
    """
    global _scan_status, _scan_started_at, _scan_completed_at, _scan_error_message

    if request is None:
        request = ScanRequest()

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
    _scan_cancelled = False

    # Launch scan as a background coroutine
    _scan_task = asyncio.create_task(_run_scan(request.regions))

    return {
        "status": "accepted",
        "message": "Scan initiated",
        "started_at": _scan_started_at,
        "regions": request.regions,
    }


@router.post("/cancel")
async def cancel_scan() -> dict[str, str]:
    """Cancel a running scan.

    Returns the scan to idle state, preserving any previously completed results.
    """
    global _scan_status, _scan_completed_at, _scan_error_message
    global _scan_task, _scan_cancelled

    if _scan_status != ScanStatus.in_progress:
        raise CloudSpyglassError(
            error_code="NO_SCAN_IN_PROGRESS",
            message="No scan is currently in progress to cancel.",
            recoverable=False,
            status_code=400,
        )

    _scan_cancelled = True

    # Cancel the background task
    if _scan_task and not _scan_task.done():
        _scan_task.cancel()

    _scan_status = ScanStatus.idle
    _scan_completed_at = datetime.now(timezone.utc).isoformat()
    _scan_error_message = "Scan cancelled by user"

    return {
        "status": "cancelled",
        "message": "Scan has been cancelled",
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
