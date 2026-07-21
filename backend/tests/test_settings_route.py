"""Unit tests for the settings API routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.routes import settings as settings_module


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset settings to defaults between tests."""
    from backend.models.settings import AppSettings

    settings_module._settings = AppSettings()
    yield
    settings_module._settings = AppSettings()


class TestGetSettings:
    """Tests for GET /api/settings."""

    async def test_returns_default_settings(self, client: AsyncClient) -> None:
        """Initial GET returns default settings (manual, no regions)."""
        response = await client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "manual"
        assert data["selected_regions"] == []

    async def test_returns_updated_settings(self, client: AsyncClient) -> None:
        """GET reflects previously applied PUT changes."""
        await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "5m",
                "selected_regions": ["us-east-1", "eu-west-1"],
            },
        )
        response = await client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "5m"
        assert data["selected_regions"] == ["us-east-1", "eu-west-1"]


class TestPutSettings:
    """Tests for PUT /api/settings."""

    async def test_update_auto_refresh_interval(self, client: AsyncClient) -> None:
        """PUT updates the auto-refresh interval."""
        response = await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "15m",
                "selected_regions": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "15m"
        assert data["selected_regions"] == []

    async def test_update_selected_regions(self, client: AsyncClient) -> None:
        """PUT updates the selected regions list."""
        response = await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "manual",
                "selected_regions": ["us-west-2", "ap-southeast-1"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "manual"
        assert data["selected_regions"] == ["us-west-2", "ap-southeast-1"]

    async def test_update_both_fields(self, client: AsyncClient) -> None:
        """PUT can update both interval and regions simultaneously."""
        response = await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "30m",
                "selected_regions": ["eu-central-1"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "30m"
        assert data["selected_regions"] == ["eu-central-1"]

    async def test_invalid_interval_returns_422(self, client: AsyncClient) -> None:
        """PUT with invalid auto_refresh_interval returns 422."""
        response = await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "invalid_value",
                "selected_regions": [],
            },
        )
        assert response.status_code == 422

    async def test_all_valid_intervals(self, client: AsyncClient) -> None:
        """PUT accepts all valid auto-refresh interval values."""
        valid_intervals = ["1m", "5m", "15m", "30m", "60m", "manual"]
        for interval in valid_intervals:
            response = await client.put(
                "/api/settings",
                json={
                    "auto_refresh_interval": interval,
                    "selected_regions": [],
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["auto_refresh_interval"] == interval

    async def test_sequential_updates_replace_settings(
        self, client: AsyncClient
    ) -> None:
        """Sequential PUTs always result in latest settings being active."""
        await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "1m",
                "selected_regions": ["us-east-1"],
            },
        )
        response = await client.put(
            "/api/settings",
            json={
                "auto_refresh_interval": "60m",
                "selected_regions": ["eu-west-1", "ap-northeast-1"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_refresh_interval"] == "60m"
        assert data["selected_regions"] == ["eu-west-1", "ap-northeast-1"]
