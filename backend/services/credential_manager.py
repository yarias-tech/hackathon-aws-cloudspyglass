"""AWS Credential Manager service with in-memory storage and STS validation."""

import asyncio
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from ..exceptions import CloudSpyglassError
from ..models.credentials import CredentialStatus, CredentialSubmission, ValidationResult


class CredentialManager:
    """In-memory credential store with STS validation.

    Stores credentials exclusively in memory (never persisted to disk).
    Falls back to the standard boto3 credential chain when no UI credentials
    are explicitly provided.
    """

    _VALIDATION_TIMEOUT_SECONDS = 10

    def __init__(self) -> None:
        self._access_key_id: str | None = None
        self._secret_access_key: str | None = None
        self._session_token: str | None = None
        self._region: str | None = None
        self._account_id: str | None = None
        self._arn: str | None = None
        self._credential_source: str | None = None
        self._connected: bool = False
        self._expiry: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def set_credentials(self, submission: CredentialSubmission) -> CredentialStatus:
        """Validate and store credentials in-memory.

        Rejects submissions where access_key_id or secret_access_key are
        empty or whitespace-only.

        Returns:
            CredentialStatus reflecting the new state after validation.

        Raises:
            CloudSpyglassError: If fields are empty/whitespace or validation fails.
        """
        # Whitespace validation (Requirement 1.6)
        if not submission.access_key_id or not submission.access_key_id.strip():
            raise CloudSpyglassError(
                error_code="INVALID_CREDENTIALS",
                message="Access Key ID is required and cannot be empty or whitespace.",
                recoverable=False,
                status_code=400,
            )
        if not submission.secret_access_key or not submission.secret_access_key.strip():
            raise CloudSpyglassError(
                error_code="INVALID_CREDENTIALS",
                message="Secret Access Key is required and cannot be empty or whitespace.",
                recoverable=False,
                status_code=400,
            )

        # Store credentials in-memory (Requirement 1.3, 1.4)
        self._access_key_id = submission.access_key_id.strip()
        self._secret_access_key = submission.secret_access_key.strip()
        self._session_token = (
            submission.session_token.strip()
            if submission.session_token and submission.session_token.strip()
            else None
        )
        self._region = submission.region
        self._credential_source = "ui"

        # Validate via STS (Requirement 2.1)
        validation = await self.validate_credentials()

        if validation.valid:
            self._connected = True
            self._account_id = validation.account_id
            self._arn = validation.arn
            # Determine expiry: session tokens imply temporary credentials
            if self._session_token:
                self._expiry = None  # Cannot determine exact expiry from STS alone
            else:
                self._expiry = "No expiration"
        else:
            # Clear credentials on validation failure
            self._clear_internal()
            raise CloudSpyglassError(
                error_code="CREDENTIAL_VALIDATION_FAILED",
                message=validation.error or "Credential validation failed.",
                recoverable=False,
                status_code=401,
            )

        return self.get_status()

    async def validate_credentials(self) -> ValidationResult:
        """Call STS GetCallerIdentity to validate current credentials.

        Uses a 10-second timeout per Requirement 2.1.

        Returns:
            ValidationResult with account_id and ARN on success, or error on failure.
        """
        try:
            session = await self.get_boto3_session()
            sts_client = session.client("sts")

            # Run the blocking STS call with a timeout
            loop = asyncio.get_event_loop()
            identity = await asyncio.wait_for(
                loop.run_in_executor(None, sts_client.get_caller_identity),
                timeout=self._VALIDATION_TIMEOUT_SECONDS,
            )

            return ValidationResult(
                valid=True,
                account_id=identity["Account"],
                arn=identity["Arn"],
            )

        except asyncio.TimeoutError:
            return ValidationResult(
                valid=False,
                error="Credential validation timed out after 10 seconds.",
            )
        except NoCredentialsError:
            return ValidationResult(
                valid=False,
                error="No AWS credentials found. Please provide credentials.",
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            error_msg = exc.response.get("Error", {}).get("Message", str(exc))

            if error_code in ("ExpiredTokenException", "ExpiredToken"):
                return ValidationResult(
                    valid=False,
                    error=f"Credentials expired: {error_msg}",
                )

            return ValidationResult(
                valid=False,
                error=f"Invalid credentials: {error_msg}",
            )
        except BotoCoreError as exc:
            return ValidationResult(
                valid=False,
                error=f"Network or configuration error: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(
                valid=False,
                error=f"Unexpected error during validation: {exc}",
            )

    async def get_boto3_session(self) -> boto3.Session:
        """Return a boto3 Session configured with current credentials.

        If UI credentials are stored, uses those. Otherwise falls back to the
        standard boto3 credential chain (env vars, shared config, instance profile).

        Requirement 1.4: Always uses the most recently submitted credentials.
        Requirement 1.5: Falls back to boto3 chain when no UI credentials.
        """
        if self._access_key_id and self._secret_access_key:
            kwargs: dict = {
                "aws_access_key_id": self._access_key_id,
                "aws_secret_access_key": self._secret_access_key,
                "region_name": self._region,
            }
            if self._session_token:
                kwargs["aws_session_token"] = self._session_token
            return boto3.Session(**kwargs)

        # Fallback to boto3 credential chain (Requirement 1.5)
        kwargs = {}
        if self._region:
            kwargs["region_name"] = self._region
        return boto3.Session(**kwargs)

    async def clear_credentials(self) -> None:
        """Remove all stored credentials and reset state.

        Requirement 2.4: Disconnect clears all credential data from memory.
        """
        self._clear_internal()

    def get_status(self) -> CredentialStatus:
        """Return the current credential connection status.

        Returns:
            CredentialStatus reflecting connected/disconnected/expired state.
        """
        if not self._connected:
            return CredentialStatus(
                connected=False,
                status="Disconnected",
            )

        return CredentialStatus(
            connected=True,
            account_id=self._account_id,
            credential_source=self._credential_source,
            expiry=self._expiry,
            status="Connected",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_internal(self) -> None:
        """Reset all internal credential state."""
        self._access_key_id = None
        self._secret_access_key = None
        self._session_token = None
        self._region = None
        self._account_id = None
        self._arn = None
        self._credential_source = None
        self._connected = False
        self._expiry = None
