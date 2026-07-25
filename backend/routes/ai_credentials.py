"""API routes for AI credential management."""

from fastapi import APIRouter

from ..dependencies import ai_credential_manager
from ..models.ai_credentials import AiCredentialStatus, AiCredentialSubmission

router = APIRouter(prefix="/api/ai-credentials", tags=["ai-credentials"])


@router.post("", response_model=AiCredentialStatus)
async def submit_ai_credentials(
    submission: AiCredentialSubmission,
) -> AiCredentialStatus:
    """Submit and validate AI API credentials.

    Receives AI credentials via POST, validates HTTPS scheme, runs a
    health check via client.models.list(), and stores them in memory if valid.

    Requirements: 9.1, 9.2, 9.3, 9.5
    """
    return await ai_credential_manager.set_credentials(submission)


@router.get("/status", response_model=AiCredentialStatus)
async def get_ai_credential_status() -> AiCredentialStatus:
    """Return the current AI credential connection status.

    Requirements: 9.4
    """
    return ai_credential_manager.get_status()


@router.delete("", response_model=AiCredentialStatus)
async def clear_ai_credentials() -> AiCredentialStatus:
    """Clear custom AI credentials and revert to environment variable fallback.

    Requirements: 9.1, 9.2, 9.3
    """
    await ai_credential_manager.clear_credentials()
    return ai_credential_manager.get_status()
