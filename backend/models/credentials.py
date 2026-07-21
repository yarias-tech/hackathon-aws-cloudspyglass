"""Pydantic models for AWS credential management."""

from typing import Literal

from pydantic import BaseModel, Field


class CredentialSubmission(BaseModel):
    """Payload for submitting AWS credentials via the UI."""

    access_key_id: str = Field(..., max_length=128)
    secret_access_key: str = Field(..., max_length=128)
    session_token: str | None = Field(None, max_length=4096)
    region: str


class CredentialStatus(BaseModel):
    """Current state of the credential connection."""

    connected: bool
    account_id: str | None = None
    credential_source: Literal["ui", "boto3_chain"] | None = None
    expiry: str | None = None  # ISO 8601 or "No expiration"
    status: Literal["Connected", "Disconnected", "Expired"]


class ValidationResult(BaseModel):
    """Result of STS GetCallerIdentity validation."""

    valid: bool
    account_id: str | None = None
    arn: str | None = None
    error: str | None = None
