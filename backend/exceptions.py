"""CloudSpyglass exception hierarchy and FastAPI error handler."""

from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from .models.errors import ErrorResponse


class CloudSpyglassError(Exception):
    """Base exception for all CloudSpyglass application errors.

    Attributes:
        error_code: UPPER_SNAKE_CASE error identifier.
        message: Human-readable description (≤500 chars).
        details: Optional additional context string.
        recoverable: True for transient errors (timeouts, throttling),
                     False for permanent errors (invalid input, auth failure).
        status_code: HTTP status code to return.
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        details: str | None = None,
        recoverable: bool = False,
        status_code: int = 500,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details
        self.recoverable = recoverable
        self.status_code = status_code


async def cloudspyglass_error_handler(
    request: Request, exc: CloudSpyglassError
) -> JSONResponse:
    """FastAPI exception handler that converts CloudSpyglassError to JSON."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            timestamp=datetime.now(timezone.utc).isoformat(),
            recoverable=exc.recoverable,
        ).model_dump(),
    )
