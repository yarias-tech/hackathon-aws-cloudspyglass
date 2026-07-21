"""Property-based tests for export filename format.

**Validates: Requirements 11.3**

Property 25: Export filename format
- For ANY Account_ID (12-digit string) and ANY ExportFormat (pdf, png, svg),
  the generated filename MUST match the pattern {Account_ID}_{YYYYMMDD_HHmmss}.{format}.
- The timestamp portion must represent a valid UTC datetime close to the current time.
"""

import re
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.export import ExportFormat
from backend.services.export_service import ExportService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid AWS account IDs: exactly 12 digits
account_id_strategy = st.from_regex(r"[0-9]{12}", fullmatch=True)

# All supported export formats
export_format_strategy = st.sampled_from([ExportFormat.PDF, ExportFormat.PNG, ExportFormat.SVG])


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

class TestExportFilenameFormat:
    """Property 25: Export filename format validation."""

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_filename_matches_full_pattern(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """The generated filename matches {Account_ID}_{YYYYMMDD_HHmmss}.{format}.

        Validates that the overall regex pattern is satisfied for any valid
        account ID and export format combination.
        """
        service = ExportService()
        filename = service._generate_filename(account_id, fmt)

        pattern = rf"^{re.escape(account_id)}_\d{{8}}_\d{{6}}\.{re.escape(fmt.value)}$"
        assert re.match(pattern, filename), (
            f"Filename '{filename}' does not match expected pattern '{pattern}'"
        )

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_filename_starts_with_account_id(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """The filename starts with the account_id followed by an underscore."""
        service = ExportService()
        filename = service._generate_filename(account_id, fmt)

        assert filename.startswith(f"{account_id}_"), (
            f"Filename '{filename}' should start with '{account_id}_'"
        )

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_timestamp_is_valid_utc_datetime(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """The timestamp portion represents a valid UTC datetime (YYYYMMDD_HHmmss).

        Extracts the timestamp from between the account_id prefix and the
        file extension, then parses it to confirm it is a real datetime.
        """
        service = ExportService()
        filename = service._generate_filename(account_id, fmt)

        # Extract timestamp: everything between "{account_id}_" and ".{format}"
        prefix = f"{account_id}_"
        suffix = f".{fmt.value}"
        assert filename.startswith(prefix) and filename.endswith(suffix)

        timestamp_str = filename[len(prefix):-len(suffix)]

        # Verify it parses as a valid datetime
        parsed = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
        assert parsed is not None, f"Could not parse timestamp '{timestamp_str}'"

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_file_extension_matches_format(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """The file extension matches the format value (pdf, png, or svg)."""
        service = ExportService()
        filename = service._generate_filename(account_id, fmt)

        expected_extension = f".{fmt.value}"
        assert filename.endswith(expected_extension), (
            f"Filename '{filename}' should end with '{expected_extension}'"
        )

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_timestamp_is_close_to_now(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """The timestamp in the filename represents a time within 5 seconds of now.

        Since _generate_filename uses datetime.now(timezone.utc), the embedded
        timestamp should be very close to the current UTC time.
        """
        before = datetime.now(timezone.utc)
        service = ExportService()
        filename = service._generate_filename(account_id, fmt)
        after = datetime.now(timezone.utc)

        # Extract timestamp
        prefix = f"{account_id}_"
        suffix = f".{fmt.value}"
        timestamp_str = filename[len(prefix):-len(suffix)]
        parsed = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S").replace(
            tzinfo=timezone.utc
        )

        # The parsed timestamp should be between before and after (with tolerance)
        assert before.replace(microsecond=0) <= parsed <= after.replace(microsecond=0) + timedelta(seconds=1), (
            f"Timestamp {parsed} not within expected range [{before}, {after}]"
        )

    @given(account_id=account_id_strategy, fmt=export_format_strategy)
    @settings(max_examples=50, deadline=10000)
    async def test_sequential_calls_produce_valid_filenames(
        self, account_id: str, fmt: ExportFormat
    ) -> None:
        """Multiple sequential calls produce correctly formatted filenames.

        Each call should independently produce a valid filename matching
        the expected pattern, though timestamps may differ between calls.
        """
        service = ExportService()
        pattern = rf"^{re.escape(account_id)}_\d{{8}}_\d{{6}}\.{re.escape(fmt.value)}$"

        filename_1 = service._generate_filename(account_id, fmt)
        filename_2 = service._generate_filename(account_id, fmt)

        assert re.match(pattern, filename_1), (
            f"First filename '{filename_1}' does not match pattern"
        )
        assert re.match(pattern, filename_2), (
            f"Second filename '{filename_2}' does not match pattern"
        )
