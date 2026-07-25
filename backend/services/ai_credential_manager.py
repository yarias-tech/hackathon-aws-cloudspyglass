"""AI Credential Manager service with in-memory storage and health-check validation."""

import asyncio
import os
from datetime import datetime, timezone

from openai import AsyncOpenAI

from ..exceptions import CloudSpyglassError
from ..models.ai_credentials import (
    AiCredentialStatus,
    AiCredentialSubmission,
    AiValidationResult,
)


class AiCredentialManager:
    """In-memory AI credential store with health-check validation.

    Stores AI API credentials exclusively in memory (never persisted to disk).
    Falls back to environment variables (AI_API_BASE_URL, AI_API_KEY, AI_API_MODEL)
    when no custom credentials are explicitly provided via the UI.
    """

    _HEALTH_CHECK_TIMEOUT_SECONDS = 10

    def __init__(self) -> None:
        self._base_url: str | None = None
        self._api_key: str | None = None
        self._model: str | None = None
        self._connected: bool = False
        self._validated_at: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def set_credentials(
        self, submission: AiCredentialSubmission
    ) -> AiCredentialStatus:
        """Validate and store AI API credentials in-memory.

        Validates that base_url uses HTTPS, then runs a health check by
        calling client.models.list(). On success, stores the credentials.
        On failure, raises CloudSpyglassError and preserves previous state.

        Returns:
            AiCredentialStatus reflecting the new state after validation.

        Raises:
            CloudSpyglassError: If HTTPS validation fails or health check fails.
        """
        # Validate HTTPS scheme (Requirement 9.5)
        if not submission.base_url.startswith("https://"):
            raise CloudSpyglassError(
                error_code="INVALID_AI_BASE_URL",
                message="AI API base URL must use HTTPS.",
                details="The base_url must start with 'https://'.",
                recoverable=False,
                status_code=400,
            )

        # Validate non-empty fields
        if not submission.api_key or not submission.api_key.strip():
            raise CloudSpyglassError(
                error_code="INVALID_AI_CREDENTIALS",
                message="AI API key is required and cannot be empty or whitespace.",
                recoverable=False,
                status_code=400,
            )
        if not submission.model or not submission.model.strip():
            raise CloudSpyglassError(
                error_code="INVALID_AI_CREDENTIALS",
                message="AI model identifier is required and cannot be empty or whitespace.",
                recoverable=False,
                status_code=400,
            )

        # Run health check before committing credentials (Requirement 9.2)
        validation = await self._validate_connection(
            base_url=submission.base_url.strip(),
            api_key=submission.api_key.strip(),
        )

        if not validation.valid:
            # Health check failed — preserve previous state
            raise CloudSpyglassError(
                error_code="AI_HEALTH_CHECK_FAILED",
                message=validation.error or "AI API health check failed.",
                recoverable=True,
                status_code=401,
            )

        # Health check succeeded — store credentials
        self._base_url = submission.base_url.strip()
        self._api_key = submission.api_key.strip()
        self._model = submission.model.strip()
        self._connected = True
        self._validated_at = datetime.now(timezone.utc).isoformat()

        return self.get_status()

    async def clear_credentials(self) -> None:
        """Remove all stored AI credentials and reset to env var fallback.

        After clearing, get_client and get_model will use environment variables.
        """
        self._clear_internal()

    def get_status(self) -> AiCredentialStatus:
        """Return the current AI credential connection status.

        Returns:
            AiCredentialStatus indicating whether credentials are configured
            and from what source (custom, environment, or none).
        """
        if self._connected:
            return AiCredentialStatus(
                connected=True,
                source="custom",
                model=self._model,
                validated_at=self._validated_at,
            )

        # Check environment variable fallback
        env_base_url = os.environ.get("AI_API_BASE_URL", "").strip()
        env_api_key = os.environ.get("AI_API_KEY", "").strip()
        env_model = os.environ.get("AI_API_MODEL", "").strip()

        if env_base_url and env_api_key and env_model:
            return AiCredentialStatus(
                connected=True,
                source="environment",
                model=env_model,
                validated_at=None,
            )

        return AiCredentialStatus(
            connected=False,
            source="none",
            model=None,
            validated_at=None,
        )

    def get_client(self) -> AsyncOpenAI:
        """Return an AsyncOpenAI client configured with current credentials.

        Uses custom credentials if set, otherwise falls back to environment
        variables (AI_API_BASE_URL, AI_API_KEY).

        Raises:
            CloudSpyglassError: If required configuration is missing.
        """
        if self._connected and self._base_url and self._api_key:
            return AsyncOpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
            )

        # Fallback to environment variables
        env_base_url = os.environ.get("AI_API_BASE_URL", "").strip()
        env_api_key = os.environ.get("AI_API_KEY", "").strip()

        if not env_base_url:
            raise CloudSpyglassError(
                error_code="AI_CONFIG_MISSING",
                message="AI API base URL is not configured.",
                details="Set AI_API_BASE_URL environment variable or provide custom credentials.",
                recoverable=False,
                status_code=400,
            )
        if not env_api_key:
            raise CloudSpyglassError(
                error_code="AI_CONFIG_MISSING",
                message="AI API key is not configured.",
                details="Set AI_API_KEY environment variable or provide custom credentials.",
                recoverable=False,
                status_code=400,
            )

        return AsyncOpenAI(
            base_url=env_base_url,
            api_key=env_api_key,
        )

    def get_model(self) -> str:
        """Return the configured AI model identifier.

        Uses custom model if set, otherwise falls back to AI_API_MODEL env var.

        Raises:
            CloudSpyglassError: If no model is configured.
        """
        if self._connected and self._model:
            return self._model

        # Fallback to environment variable
        env_model = os.environ.get("AI_API_MODEL", "").strip()

        if not env_model:
            raise CloudSpyglassError(
                error_code="AI_CONFIG_MISSING",
                message="AI model identifier is not configured.",
                details="Set AI_API_MODEL environment variable or provide custom credentials.",
                recoverable=False,
                status_code=400,
            )

        return env_model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _validate_connection(
        self, base_url: str, api_key: str
    ) -> AiValidationResult:
        """Run a health check against the AI API by calling client.models.list().

        Uses a 10-second timeout. Never logs or exposes the api_key value.

        Returns:
            AiValidationResult with valid=True on success, or error on failure.
        """
        try:
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)

            await asyncio.wait_for(
                client.models.list(),
                timeout=self._HEALTH_CHECK_TIMEOUT_SECONDS,
            )

            return AiValidationResult(valid=True)

        except asyncio.TimeoutError:
            return AiValidationResult(
                valid=False,
                error="AI API health check timed out after 10 seconds.",
            )
        except Exception as exc:  # noqa: BLE001
            # Never include api_key in error messages (Requirement 9.6)
            error_msg = str(exc)
            # Sanitize: strip any potential key leakage from error messages
            if api_key in error_msg:
                error_msg = error_msg.replace(api_key, "***")
            return AiValidationResult(
                valid=False,
                error=f"AI API health check failed: {error_msg}",
            )

    def _clear_internal(self) -> None:
        """Reset all internal AI credential state."""
        self._base_url = None
        self._api_key = None
        self._model = None
        self._connected = False
        self._validated_at = None
