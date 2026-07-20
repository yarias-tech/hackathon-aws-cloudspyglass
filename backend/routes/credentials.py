"""API routes for AWS credential management."""

from fastapi import APIRouter

from ..models.credentials import CredentialStatus, CredentialSubmission
from ..services.credential_manager import CredentialManager

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

# Module-level singleton (no DI container yet)
_credential_manager = CredentialManager()


@router.post("", response_model=CredentialStatus)
async def submit_credentials(submission: CredentialSubmission) -> CredentialStatus:
    """Submit and validate AWS credentials.

    Receives credentials via POST, validates them using STS GetCallerIdentity,
    and stores them in memory if valid.

    Requirements: 1.2, 2.1
    """
    return await _credential_manager.set_credentials(submission)


@router.get("/status", response_model=CredentialStatus)
async def get_credential_status() -> CredentialStatus:
    """Return the current credential connection status.

    Requirements: 2.5
    """
    return _credential_manager.get_status()


@router.delete("", response_model=CredentialStatus)
async def clear_credentials() -> CredentialStatus:
    """Clear all stored credentials from memory.

    Requirements: 2.4, 2.5
    """
    await _credential_manager.clear_credentials()
    return _credential_manager.get_status()
