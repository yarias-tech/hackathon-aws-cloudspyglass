"""Pydantic models for AI credential management."""

from typing import Literal

from pydantic import BaseModel, Field


class AiCredentialSubmission(BaseModel):
    """Payload for submitting AI API credentials via the UI."""

    base_url: str = Field(..., max_length=512)
    api_key: str = Field(..., max_length=512)
    model: str = Field(..., max_length=256)


class AiCredentialStatus(BaseModel):
    """Current state of the AI credential connection."""

    connected: bool
    source: Literal["custom", "environment", "none"] = "none"
    model: str | None = None
    validated_at: str | None = None  # ISO 8601


class AiValidationResult(BaseModel):
    """Result of AI API health-check validation."""

    valid: bool
    error: str | None = None
