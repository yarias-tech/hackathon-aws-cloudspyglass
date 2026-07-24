"""API routes for triggering and monitoring infrastructure scans."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..dependencies import get_relationship_resolver, scan_storage
from ..exceptions import CloudSpyglassError
from ..models.scan import ScanRequest, ScanResult
from ..services.scanner import Scanner
from ..services.session_manager import SessionState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanProgress(BaseModel):
    """Response model for GET /api/scan/status."""

    status: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    total_resources: int | None = None
    total_regions: int | None = None
    total_failures: int | None = None


async def _run_scan(session: SessionState, regions: list[str] | None, generation: int) -> None:
    """Execute the scan in the background, updating session state."""
    try:
        scanner_instance = Scanner(session.credential_manager)
        result = await scanner_instance.scan(regions=regions)

        # Check if this scan is still the current one
        if generation != session.scan_generation:
            return

        # Resolve relationships
        account_id = result.account_id
        if account_id and result.resources:
            try:
                resolver = get_relationship_resolver(account_id)
                relationships, unresolved = resolver.resolve(result.resources)
                result.relationships = relationships
                result.resources.extend(unresolved)
            except Exception as rel_exc:
                logger.warning("Relationship resolution failed: %s", rel_exc)

        if generation != session.scan_generation:
            return

        session.last_scan_result = result
        session.scan_status = "completed"
        session.scan_completed_at = datetime.now(timezone.utc).isoformat()
        session.scan_error_message = None

        # Persist scan result
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
        if generation == session.scan_generation:
            session.scan_status = "idle"
            session.scan_completed_at = datetime.now(timezone.utc).isoformat()
            session.scan_error_message = "Scan cancelled by user"
        logger.info("Scan generation %d cancelled", generation)
    except Exception as exc:
        if generation == session.scan_generation:
            session.scan_status = "failed"
            session.scan_completed_at = datetime.now(timezone.utc).isoformat()
            session.scan_error_message = str(exc)
        logger.exception("Scan failed: %s", exc)


def get_last_scan_result_from_session(request: Request) -> ScanResult | None:
    """Return the most recent scan result for the current session."""
    session = request.state.session
    return session.last_scan_result


@router.post("")
async def trigger_scan(request: Request, scan_request: ScanRequest | None = None) -> dict[str, Any]:
    """Trigger a new infrastructure scan.

    Requirements: 3.1, 3.2
    """
    session = request.state.session

    if scan_request is None:
        scan_request = ScanRequest()

    if session.scan_status == "in_progress":
        raise CloudSpyglassError(
            error_code="SCAN_IN_PROGRESS",
            message="A scan is already in progress. Please wait for it to complete.",
            details=f"Scan started at {session.scan_started_at}",
            recoverable=False,
            status_code=409,
        )

    # Transition to in_progress
    session.scan_status = "in_progress"
    session.scan_started_at = datetime.now(timezone.utc).isoformat()
    session.scan_completed_at = None
    session.scan_error_message = None
    session.scan_generation += 1

    # Cancel any previous task
    if session.scan_task and not session.scan_task.done():
        session.scan_task.cancel()

    # Launch scan as background task
    session.scan_task = asyncio.create_task(
        _run_scan(session, scan_request.regions, session.scan_generation)
    )

    return {
        "status": "accepted",
        "message": "Scan initiated",
        "started_at": session.scan_started_at,
        "regions": scan_request.regions,
    }


@router.post("/cancel")
async def cancel_scan(request: Request) -> dict[str, str]:
    """Cancel a running scan."""
    session = request.state.session

    if session.scan_status != "in_progress":
        raise CloudSpyglassError(
            error_code="NO_SCAN_IN_PROGRESS",
            message="No scan is currently in progress to cancel.",
            recoverable=False,
            status_code=400,
        )

    session.scan_generation += 1

    if session.scan_task and not session.scan_task.done():
        session.scan_task.cancel()

    session.scan_status = "idle"
    session.scan_completed_at = datetime.now(timezone.utc).isoformat()
    session.scan_error_message = "Scan cancelled by user"

    return {
        "status": "cancelled",
        "message": "Scan has been cancelled",
    }


@router.get("/status", response_model=ScanProgress)
async def get_scan_status(request: Request) -> ScanProgress:
    """Return the current scan progress/status.

    Requirements: 3.1, 3.2
    """
    session = request.state.session

    progress = ScanProgress(
        status=session.scan_status,
        started_at=session.scan_started_at,
        completed_at=session.scan_completed_at,
        error_message=session.scan_error_message,
    )

    if session.last_scan_result is not None:
        progress.total_resources = len(session.last_scan_result.resources)
        progress.total_regions = len(session.last_scan_result.scanned_regions)
        progress.total_failures = len(session.last_scan_result.failures)

    return progress
