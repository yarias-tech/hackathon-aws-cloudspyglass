"""API routes for AI architecture advisor analysis."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..dependencies import advisor_service, credential_manager
from ..exceptions import CloudSpyglassError
from ..models.advisor import AdvisorResponse, AdvisorStatus, AnalyzeRequest

router = APIRouter(prefix="/api/advisor", tags=["advisor"])


@router.post("/analyze")
async def analyze(request: AnalyzeRequest) -> JSONResponse:
    """Trigger an architecture analysis for the connected AWS account.

    Validates that an AWS account is connected, then starts a background
    analysis task. Returns HTTP 202 immediately with the task_id.

    Requirements: Design — Architecture Analysis Flow
    """
    status = credential_manager.get_status()
    if not status.connected or not status.account_id:
        raise CloudSpyglassError(
            error_code="NO_ACCOUNT_CONNECTED",
            message="An AWS account must be connected before requesting analysis.",
            recoverable=False,
            status_code=400,
        )

    task_id = await advisor_service.start_analysis(
        pillars=request.pillars, account_id=status.account_id
    )

    return JSONResponse(status_code=202, content={"task_id": task_id})


@router.get("/status", response_model=AdvisorStatus)
async def get_status() -> AdvisorStatus:
    """Return the current advisor analysis status.

    Requirements: Design — GET /api/advisor/status
    """
    result = advisor_service.get_status()
    return AdvisorStatus(status=result["status"], task_id=result["task_id"])


@router.get("/results", response_model=AdvisorResponse)
async def get_results() -> AdvisorResponse | JSONResponse:
    """Return the latest architecture analysis results.

    Returns 404 if no results are available.

    Requirements: Design — GET /api/advisor/results
    """
    results = advisor_service.get_results()
    if results is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "NO_RESULTS", "message": "No analysis results available."},
        )
    return results
