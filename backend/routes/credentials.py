"""API routes for AWS credential management."""

from fastapi import APIRouter, Request

from ..models.credentials import CredentialStatus, CredentialSubmission

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.post("", response_model=CredentialStatus)
async def submit_credentials(submission: CredentialSubmission, request: Request) -> CredentialStatus:
    """Submit and validate AWS credentials.

    Requirements: 1.2, 2.1
    """
    session = request.state.session
    return await session.credential_manager.set_credentials(submission)


@router.get("/status", response_model=CredentialStatus)
async def get_credential_status(request: Request) -> CredentialStatus:
    """Return the current credential connection status.

    Requirements: 2.5
    """
    session = request.state.session
    return session.credential_manager.get_status()


@router.delete("", response_model=CredentialStatus)
async def clear_credentials(request: Request) -> CredentialStatus:
    """Clear all stored credentials from memory.

    Requirements: 2.4, 2.5
    """
    session = request.state.session
    await session.credential_manager.clear_credentials()
    return session.credential_manager.get_status()
