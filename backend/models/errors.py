"""Pydantic model for standardized API error responses."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response structure for all CloudSpyglass API errors.

    All error responses conform to requirements 14.1-14.3:
    - error_code: UPPER_SNAKE_CASE identifier
    - message: human-readable description (≤500 chars)
    - details: optional additional context
    - timestamp: ISO 8601 UTC
    - recoverable: true for transient errors, false for permanent errors
    """

    error_code: str  # UPPER_SNAKE_CASE
    message: str = Field(..., max_length=500)
    details: str | None = None
    timestamp: str  # ISO 8601 UTC
    recoverable: bool
