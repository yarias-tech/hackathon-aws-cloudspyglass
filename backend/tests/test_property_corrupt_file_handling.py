"""Property-based tests for corrupt file graceful handling.

**Validates: Requirements 10.6**

Property 24: Corrupt file graceful handling
- For any file content at `data/{account_id}.json` that is not valid UTF-8 JSON
  or does not conform to the ScanResult schema, the system SHALL discard it and
  return no scan data (empty state).
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.services.scan_storage import ScanStorage


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid AWS account IDs: exactly 12 digits
account_id_strategy = st.from_regex(r"[0-9]{12}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_storage() -> tuple[ScanStorage, Path]:
    """Create a ScanStorage with a fresh temporary directory."""
    tmp_dir = Path(tempfile.mkdtemp())
    data_dir = tmp_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return ScanStorage(data_dir=data_dir), data_dir


# ---------------------------------------------------------------------------
# Property 24: Corrupt file graceful handling
# ---------------------------------------------------------------------------


class TestCorruptFileHandling:
    """Corrupt or invalid files are discarded and load() returns None."""

    @given(account_id=account_id_strategy, data=st.binary(min_size=1))
    @settings(max_examples=50, deadline=10000)
    async def test_invalid_utf8_bytes_returns_none(
        self, account_id: str, data: bytes
    ) -> None:
        """When the file contains invalid UTF-8 bytes, load() returns None.

        **Validates: Requirements 10.6**
        """
        # Ensure data is not accidentally valid UTF-8
        try:
            data.decode("utf-8")
            # If it decodes successfully, force invalid UTF-8 by adding known bad bytes
            data = b"\xff\xfe" + data + b"\x80\x81\xfe\xff"
        except UnicodeDecodeError:
            pass  # Already invalid UTF-8, use as-is

        storage, data_dir = _make_storage()
        file_path = data_dir / f"{account_id}.json"

        # Write raw bytes that are not valid UTF-8
        file_path.write_bytes(data)

        result = await storage.load(account_id)
        assert result is None, (
            "load() should return None for invalid UTF-8 content"
        )

    @given(
        account_id=account_id_strategy,
        text_content=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=50, deadline=10000)
    async def test_invalid_json_returns_none(
        self, account_id: str, text_content: str
    ) -> None:
        """When the file contains valid UTF-8 but not valid JSON, load() returns None.

        **Validates: Requirements 10.6**
        """
        # Ensure the text is NOT valid JSON
        try:
            json.loads(text_content)
            # If it parses as JSON, skip this example
            assume(False)
        except (json.JSONDecodeError, ValueError):
            pass  # Good — it's not valid JSON

        storage, data_dir = _make_storage()
        file_path = data_dir / f"{account_id}.json"

        file_path.write_text(text_content, encoding="utf-8")

        result = await storage.load(account_id)
        assert result is None, (
            "load() should return None for non-JSON text content"
        )

    @given(
        account_id=account_id_strategy,
        bad_json=st.fixed_dictionaries({
            "unexpected_key": st.text(min_size=1, max_size=20),
            "number_field": st.integers(min_value=0, max_value=9999),
        }),
    )
    @settings(max_examples=50, deadline=10000)
    async def test_schema_violating_json_returns_none(
        self, account_id: str, bad_json: dict
    ) -> None:
        """When the file contains valid JSON but doesn't conform to ScanResult schema,
        load() returns None.

        **Validates: Requirements 10.6**
        """
        storage, data_dir = _make_storage()
        file_path = data_dir / f"{account_id}.json"

        # Write valid JSON that does NOT match ScanResult schema
        file_path.write_text(json.dumps(bad_json), encoding="utf-8")

        result = await storage.load(account_id)
        assert result is None, (
            "load() should return None for schema-violating JSON"
        )

    @given(account_id=account_id_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_empty_file_returns_none(self, account_id: str) -> None:
        """When the file is empty (zero bytes), load() returns None.

        **Validates: Requirements 10.6**
        """
        storage, data_dir = _make_storage()
        file_path = data_dir / f"{account_id}.json"

        # Write empty file
        file_path.write_text("", encoding="utf-8")

        result = await storage.load(account_id)
        assert result is None, (
            "load() should return None for an empty file"
        )

    @given(
        account_id=account_id_strategy,
        truncation_point=st.integers(min_value=5, max_value=50),
    )
    @settings(max_examples=50, deadline=10000)
    async def test_truncated_json_returns_none(
        self, account_id: str, truncation_point: int
    ) -> None:
        """When the file contains truncated (partial) JSON, load() returns None.

        **Validates: Requirements 10.6**
        """
        storage, data_dir = _make_storage()
        file_path = data_dir / f"{account_id}.json"

        # Build valid-looking JSON structure, then truncate it
        valid_json = json.dumps({
            "account_id": account_id,
            "scan_timestamp": "2024-01-01T00:00:00Z",
            "resources": [{"arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-abc"}],
            "relationships": [],
            "failures": [],
            "scanned_regions": ["us-east-1"],
            "total_scan_duration_ms": 1000,
        })

        # Truncate somewhere in the middle
        actual_point = min(truncation_point, len(valid_json) - 1)
        truncated = valid_json[:actual_point]

        # Ensure it's actually invalid JSON after truncation
        try:
            parsed = json.loads(truncated)
            # If it happens to parse, it shouldn't be a valid ScanResult
            # (very unlikely but handle it)
            from backend.models.scan import ScanResult
            from pydantic import ValidationError
            try:
                ScanResult.model_validate(parsed)
                # Extremely unlikely — skip this example
                assume(False)
            except (ValidationError, TypeError, AttributeError):
                pass  # Good — schema violation
        except (json.JSONDecodeError, ValueError):
            pass  # Good — invalid JSON

        file_path.write_text(truncated, encoding="utf-8")

        result = await storage.load(account_id)
        assert result is None, (
            "load() should return None for truncated JSON content"
        )
