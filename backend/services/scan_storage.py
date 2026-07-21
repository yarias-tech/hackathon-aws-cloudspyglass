"""Atomic file-based persistence for scan results."""

import json
import logging
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from ..exceptions import CloudSpyglassError
from ..models.scan import ScanResult

logger = logging.getLogger(__name__)

# Default data directory path (relative to workspace root inside Docker)
_DEFAULT_DATA_DIR = Path("/workspace/data")


class ScanStorage:
    """Atomic file-based persistence for scan results.

    Stores one ScanResult per Account_ID as UTF-8 JSON in the data/ directory.
    Uses atomic writes (temp file + os.replace) to prevent partial writes.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DEFAULT_DATA_DIR

    async def save(self, account_id: str, scan_result: ScanResult) -> None:
        """Persist a ScanResult to disk using atomic write.

        Writes to a temporary file first, then atomically replaces the target
        file to prevent partial writes on failure.

        Args:
            account_id: AWS account identifier used as the filename.
            scan_result: The scan result to persist.

        Raises:
            CloudSpyglassError: If writing fails (STORAGE_WRITE_FAILED).
        """
        self._ensure_data_dir()
        target_path = self._get_path(account_id)

        try:
            json_data = scan_result.model_dump_json(indent=2)

            # Write to a temp file in the same directory, then atomically replace.
            # Using the same directory ensures os.replace works (same filesystem).
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._data_dir),
                prefix=f".{account_id}_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                    tmp_file.write(json_data)
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())

                # Atomic replace — either fully succeeds or target is unchanged
                os.replace(tmp_path, str(target_path))
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

        except CloudSpyglassError:
            raise
        except Exception as exc:
            logger.error("Failed to save scan result for account %s: %s", account_id, exc)
            raise CloudSpyglassError(
                error_code="STORAGE_WRITE_FAILED",
                message=f"Failed to persist scan result to disk for account {account_id}.",
                details=str(exc),
                recoverable=True,
                status_code=500,
            ) from exc

    async def load(self, account_id: str) -> ScanResult | None:
        """Load a persisted ScanResult from disk.

        Returns None if the file does not exist or is corrupt/invalid.
        Corrupt files are discarded (deleted) to prevent repeated failures.

        Args:
            account_id: AWS account identifier to load.

        Returns:
            The deserialized ScanResult, or None if missing/corrupt.
        """
        target_path = self._get_path(account_id)

        if not target_path.exists():
            return None

        try:
            raw_content = target_path.read_text(encoding="utf-8")
            data = json.loads(raw_content)
            return ScanResult.model_validate(data)
        except (
            json.JSONDecodeError,
            ValidationError,
            UnicodeDecodeError,
            ValueError,
            KeyError,
        ) as exc:
            # File is corrupt or invalid — discard it and return None
            logger.warning(
                "Discarding corrupt scan file for account %s: %s", account_id, exc
            )
            try:
                target_path.unlink()
            except OSError as unlink_exc:
                logger.error(
                    "Failed to remove corrupt file %s: %s", target_path, unlink_exc
                )
            return None
        except OSError as exc:
            logger.error("Failed to read scan file for account %s: %s", account_id, exc)
            return None

    async def exists(self, account_id: str) -> bool:
        """Check whether a persisted scan result exists for the given account.

        Args:
            account_id: AWS account identifier to check.

        Returns:
            True if a scan result file exists, False otherwise.
        """
        return self._get_path(account_id).exists()

    def _get_path(self, account_id: str) -> Path:
        """Construct the file path for a given account ID.

        Args:
            account_id: AWS account identifier.

        Returns:
            Path to the JSON file: data/{account_id}.json
        """
        return self._data_dir / f"{account_id}.json"

    def _ensure_data_dir(self) -> None:
        """Create the data directory if it does not exist."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
