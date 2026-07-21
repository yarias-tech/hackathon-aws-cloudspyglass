"""Unit tests for the scan API routes."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.scan import ScanResult
from backend.routes import scan as scan_module


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_scan_state():
    """Reset the scan module state between tests."""
    scan_module._scan_status = scan_module.ScanStatus.idle
    scan_module._scan_started_at = None
    scan_module._scan_completed_at = None
    scan_module._scan_error_message = None
    scan_module._last_scan_result = None
    yield
    scan_module._scan_status = scan_module.ScanStatus.idle
    scan_module._scan_started_at = None
    scan_module._scan_completed_at = None
    scan_module._scan_error_message = None
    scan_module._last_scan_result = None


class TestPostScan:
    """Tests for POST /api/scan."""

    async def test_trigger_scan_returns_accepted(self, client: AsyncClient) -> None:
        """POST /api/scan returns accepted status when no scan is running."""
        with patch.object(
            scan_module, "_run_scan", new_callable=AsyncMock
        ) as mock_run:
            response = await client.post("/api/scan", json={"regions": ["us-east-1"]})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"
            assert data["message"] == "Scan initiated"
            assert data["started_at"] is not None
            assert data["regions"] == ["us-east-1"]

    async def test_trigger_scan_no_regions(self, client: AsyncClient) -> None:
        """POST /api/scan with no regions passes None (discover all)."""
        with patch.object(scan_module, "_run_scan", new_callable=AsyncMock):
            response = await client.post("/api/scan", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"
            assert data["regions"] is None

    async def test_duplicate_scan_returns_409(self, client: AsyncClient) -> None:
        """POST /api/scan while scan is in progress returns SCAN_IN_PROGRESS error."""
        # Simulate an in-progress scan
        scan_module._scan_status = scan_module.ScanStatus.in_progress
        scan_module._scan_started_at = "2024-01-01T00:00:00+00:00"

        response = await client.post("/api/scan", json={"regions": ["us-east-1"]})
        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "SCAN_IN_PROGRESS"
        assert data["recoverable"] is False
        assert "already in progress" in data["message"]

    async def test_scan_after_completed_is_allowed(self, client: AsyncClient) -> None:
        """POST /api/scan is allowed after a previous scan completed."""
        scan_module._scan_status = scan_module.ScanStatus.completed

        with patch.object(scan_module, "_run_scan", new_callable=AsyncMock):
            response = await client.post("/api/scan", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"

    async def test_scan_after_failed_is_allowed(self, client: AsyncClient) -> None:
        """POST /api/scan is allowed after a previous scan failed."""
        scan_module._scan_status = scan_module.ScanStatus.failed

        with patch.object(scan_module, "_run_scan", new_callable=AsyncMock):
            response = await client.post("/api/scan", json={})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"


class TestGetScanStatus:
    """Tests for GET /api/scan/status."""

    async def test_initial_status_is_idle(self, client: AsyncClient) -> None:
        """GET /api/scan/status returns idle when no scan has been triggered."""
        response = await client.get("/api/scan/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"
        assert data["started_at"] is None
        assert data["completed_at"] is None
        assert data["error_message"] is None
        assert data["total_resources"] is None
        assert data["total_regions"] is None
        assert data["total_failures"] is None

    async def test_status_in_progress(self, client: AsyncClient) -> None:
        """GET /api/scan/status reflects in_progress state."""
        scan_module._scan_status = scan_module.ScanStatus.in_progress
        scan_module._scan_started_at = "2024-01-01T12:00:00+00:00"

        response = await client.get("/api/scan/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["started_at"] == "2024-01-01T12:00:00+00:00"
        assert data["completed_at"] is None

    async def test_status_completed_with_result(self, client: AsyncClient) -> None:
        """GET /api/scan/status returns resource counts after scan completes."""
        scan_module._scan_status = scan_module.ScanStatus.completed
        scan_module._scan_started_at = "2024-01-01T12:00:00+00:00"
        scan_module._scan_completed_at = "2024-01-01T12:05:00+00:00"
        scan_module._last_scan_result = ScanResult(
            account_id="123456789012",
            scan_timestamp="2024-01-01T12:05:00+00:00",
            resources=[],
            relationships=[],
            failures=[],
            scanned_regions=["us-east-1", "eu-west-1"],
            total_scan_duration_ms=5000,
        )

        response = await client.get("/api/scan/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["total_resources"] == 0
        assert data["total_regions"] == 2
        assert data["total_failures"] == 0

    async def test_status_failed_with_error(self, client: AsyncClient) -> None:
        """GET /api/scan/status shows error message when scan fails."""
        scan_module._scan_status = scan_module.ScanStatus.failed
        scan_module._scan_started_at = "2024-01-01T12:00:00+00:00"
        scan_module._scan_completed_at = "2024-01-01T12:00:05+00:00"
        scan_module._scan_error_message = "Invalid credentials"

        response = await client.get("/api/scan/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Invalid credentials"
