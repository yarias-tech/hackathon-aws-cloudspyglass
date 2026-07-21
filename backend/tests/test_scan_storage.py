"""Unit tests for the ScanStorage service."""

import json
import os
from pathlib import Path

import pytest

from backend.exceptions import CloudSpyglassError
from backend.models.scan import ScanResult
from backend.services.scan_storage import ScanStorage


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def storage(tmp_data_dir: Path) -> ScanStorage:
    """Create a ScanStorage instance with a temporary directory."""
    return ScanStorage(data_dir=tmp_data_dir)


@pytest.fixture
def sample_scan_result() -> ScanResult:
    """Create a minimal valid ScanResult for testing."""
    return ScanResult(
        account_id="123456789012",
        scan_timestamp="2024-01-15T10:30:00Z",
        resources=[],
        relationships=[],
        failures=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1500,
    )


@pytest.fixture
def scan_result_with_resources() -> ScanResult:
    """Create a ScanResult with some resources for testing."""
    return ScanResult(
        account_id="987654321098",
        scan_timestamp="2024-02-20T14:00:00Z",
        resources=[
            {
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-abc123",
                "resource_type": "ec2",
                "name": "my-instance",
                "region": "us-east-1",
                "tags": {"Name": "my-instance", "Environment": "prod"},
            }
        ],
        relationships=[
            {
                "source_arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-abc123",
                "target_arn": "arn:aws:ec2:us-east-1:987654321098:security-group/sg-123",
                "category": "network",
                "derived_from": "SecurityGroups",
            }
        ],
        failures=[],
        scanned_regions=["us-east-1", "us-west-2"],
        total_scan_duration_ms=5000,
    )


class TestSave:
    """Tests for the save() method."""

    async def test_saves_scan_result_as_json(
        self, storage: ScanStorage, sample_scan_result: ScanResult, tmp_data_dir: Path
    ) -> None:
        """Save creates a JSON file at data/{account_id}.json."""
        await storage.save("123456789012", sample_scan_result)

        file_path = tmp_data_dir / "123456789012.json"
        assert file_path.exists()

        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content["account_id"] == "123456789012"
        assert content["scan_timestamp"] == "2024-01-15T10:30:00Z"

    async def test_save_creates_valid_utf8_json(
        self, storage: ScanStorage, sample_scan_result: ScanResult, tmp_data_dir: Path
    ) -> None:
        """Saved file is valid UTF-8 encoded JSON."""
        await storage.save("123456789012", sample_scan_result)

        file_path = tmp_data_dir / "123456789012.json"
        raw_bytes = file_path.read_bytes()
        # Should decode as UTF-8 without error
        text = raw_bytes.decode("utf-8")
        # Should be valid JSON
        parsed = json.loads(text)
        assert isinstance(parsed, dict)

    async def test_save_overwrites_existing_file(
        self, storage: ScanStorage, tmp_data_dir: Path
    ) -> None:
        """Sequential saves for same account overwrite the previous file."""
        first = ScanResult(
            account_id="111111111111",
            scan_timestamp="2024-01-01T00:00:00Z",
            resources=[],
            relationships=[],
            scanned_regions=["us-east-1"],
            total_scan_duration_ms=1000,
        )
        second = ScanResult(
            account_id="111111111111",
            scan_timestamp="2024-01-02T00:00:00Z",
            resources=[],
            relationships=[],
            scanned_regions=["us-west-2"],
            total_scan_duration_ms=2000,
        )

        await storage.save("111111111111", first)
        await storage.save("111111111111", second)

        file_path = tmp_data_dir / "111111111111.json"
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content["scan_timestamp"] == "2024-01-02T00:00:00Z"
        assert content["scanned_regions"] == ["us-west-2"]

    async def test_save_creates_data_dir_if_missing(self, tmp_path: Path) -> None:
        """Save creates the data directory if it does not exist."""
        data_dir = tmp_path / "nonexistent" / "data"
        storage = ScanStorage(data_dir=data_dir)

        result = ScanResult(
            account_id="222222222222",
            scan_timestamp="2024-01-01T00:00:00Z",
            resources=[],
            relationships=[],
            scanned_regions=["us-east-1"],
            total_scan_duration_ms=500,
        )

        await storage.save("222222222222", result)
        assert (data_dir / "222222222222.json").exists()

    async def test_save_no_temp_files_left_on_success(
        self, storage: ScanStorage, sample_scan_result: ScanResult, tmp_data_dir: Path
    ) -> None:
        """Successful save leaves no temp files behind."""
        await storage.save("123456789012", sample_scan_result)

        files = list(tmp_data_dir.iterdir())
        assert len(files) == 1
        assert files[0].name == "123456789012.json"

    async def test_save_raises_on_write_failure(
        self, storage: ScanStorage, tmp_data_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Save raises STORAGE_WRITE_FAILED when write cannot complete."""
        import tempfile

        # Simulate failure by making mkstemp raise an OSError
        def failing_mkstemp(**kwargs):
            raise OSError("Simulated disk full")

        monkeypatch.setattr(tempfile, "mkstemp", failing_mkstemp)

        result = ScanResult(
            account_id="333333333333",
            scan_timestamp="2024-01-01T00:00:00Z",
            resources=[],
            relationships=[],
            scanned_regions=["us-east-1"],
            total_scan_duration_ms=100,
        )

        with pytest.raises(CloudSpyglassError) as exc_info:
            await storage.save("333333333333", result)

        assert exc_info.value.error_code == "STORAGE_WRITE_FAILED"
        assert exc_info.value.recoverable is True
        assert exc_info.value.status_code == 500


class TestLoad:
    """Tests for the load() method."""

    async def test_load_returns_saved_result(
        self, storage: ScanStorage, sample_scan_result: ScanResult
    ) -> None:
        """Load returns the previously saved ScanResult."""
        await storage.save("123456789012", sample_scan_result)
        loaded = await storage.load("123456789012")

        assert loaded is not None
        assert loaded.account_id == "123456789012"
        assert loaded.scan_timestamp == "2024-01-15T10:30:00Z"
        assert loaded.scanned_regions == ["us-east-1"]
        assert loaded.total_scan_duration_ms == 1500

    async def test_load_with_resources(
        self, storage: ScanStorage, scan_result_with_resources: ScanResult
    ) -> None:
        """Load correctly deserializes resources and relationships."""
        await storage.save("987654321098", scan_result_with_resources)
        loaded = await storage.load("987654321098")

        assert loaded is not None
        assert len(loaded.resources) == 1
        assert loaded.resources[0].arn == "arn:aws:ec2:us-east-1:987654321098:instance/i-abc123"
        assert loaded.resources[0].tags == {"Name": "my-instance", "Environment": "prod"}
        assert len(loaded.relationships) == 1
        assert loaded.relationships[0].category == "network"

    async def test_load_returns_none_for_missing_file(self, storage: ScanStorage) -> None:
        """Load returns None when no file exists for the account."""
        result = await storage.load("nonexistent_account")
        assert result is None

    async def test_load_returns_none_for_invalid_json(
        self, storage: ScanStorage, tmp_data_dir: Path
    ) -> None:
        """Load returns None for a file with invalid JSON content."""
        bad_file = tmp_data_dir / "bad_json.json"
        bad_file.write_text("this is not json {{{", encoding="utf-8")

        result = await storage.load("bad_json")
        assert result is None

    async def test_load_returns_none_for_invalid_schema(
        self, storage: ScanStorage, tmp_data_dir: Path
    ) -> None:
        """Load returns None for valid JSON that doesn't match ScanResult schema."""
        bad_file = tmp_data_dir / "bad_schema.json"
        bad_file.write_text(json.dumps({"foo": "bar", "not": "a scan result"}), encoding="utf-8")

        result = await storage.load("bad_schema")
        assert result is None

    async def test_load_discards_corrupt_file(
        self, storage: ScanStorage, tmp_data_dir: Path
    ) -> None:
        """Load deletes a corrupt file after detecting it."""
        corrupt_file = tmp_data_dir / "corrupt.json"
        corrupt_file.write_text("not valid json!!", encoding="utf-8")

        result = await storage.load("corrupt")
        assert result is None
        # File should be removed
        assert not corrupt_file.exists()

    async def test_load_returns_none_for_empty_file(
        self, storage: ScanStorage, tmp_data_dir: Path
    ) -> None:
        """Load returns None for an empty file."""
        empty_file = tmp_data_dir / "empty.json"
        empty_file.write_text("", encoding="utf-8")

        result = await storage.load("empty")
        assert result is None


class TestExists:
    """Tests for the exists() method."""

    async def test_exists_returns_false_when_no_file(self, storage: ScanStorage) -> None:
        """Exists returns False when no file exists for the account."""
        assert await storage.exists("nonexistent") is False

    async def test_exists_returns_true_after_save(
        self, storage: ScanStorage, sample_scan_result: ScanResult
    ) -> None:
        """Exists returns True after a successful save."""
        await storage.save("123456789012", sample_scan_result)
        assert await storage.exists("123456789012") is True


class TestGetPath:
    """Tests for the _get_path() helper method."""

    def test_path_uses_account_id_as_filename(self, storage: ScanStorage, tmp_data_dir: Path) -> None:
        """Path is data_dir/{account_id}.json."""
        path = storage._get_path("123456789012")
        assert path == tmp_data_dir / "123456789012.json"
