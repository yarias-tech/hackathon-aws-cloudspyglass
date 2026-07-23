"""API routes for AWS credential management."""

from fastapi import APIRouter

from ..dependencies import credential_manager
from ..models.credentials import CredentialStatus, CredentialSubmission

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.post("", response_model=CredentialStatus)
async def submit_credentials(submission: CredentialSubmission) -> CredentialStatus:
    """Submit and validate AWS credentials.

    Receives credentials via POST, validates them using STS GetCallerIdentity,
    and stores them in memory if valid.

    Requirements: 1.2, 2.1
    """
    return await credential_manager.set_credentials(submission)


@router.get("/status", response_model=CredentialStatus)
async def get_credential_status() -> CredentialStatus:
    """Return the current credential connection status.

    Requirements: 2.5
    """
    return credential_manager.get_status()


@router.delete("", response_model=CredentialStatus)
async def clear_credentials() -> CredentialStatus:
    """Clear all stored credentials from memory.

    Requirements: 2.4, 2.5
    """
    await credential_manager.clear_credentials()
    return credential_manager.get_status()
