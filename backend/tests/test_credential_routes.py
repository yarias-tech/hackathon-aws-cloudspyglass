"""Unit tests for the credential API routes."""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from backend.main import app
from backend.dependencies import credential_manager as _credential_manager


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_credential_manager():
    """Reset the credential manager singleton between tests."""
    _credential_manager._clear_internal()
    yield
    _credential_manager._clear_internal()


class TestPostCredentials:
    """Tests for POST /api/credentials."""

    async def test_valid_credentials_returns_connected(
        self, client: AsyncClient, aws_credentials
    ) -> None:
        """Valid credentials return connected status."""
        with mock_aws():
            response = await client.post(
                "/api/credentials",
                json={
                    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "session_token": None,
                    "region": "us-east-1",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is True
            assert data["status"] == "Connected"
            assert data["account_id"] is not None
            assert data["credential_source"] == "ui"

    async def test_empty_access_key_returns_400(self, client: AsyncClient) -> None:
        """Empty access_key_id returns 400 with error response."""
        response = await client.post(
            "/api/credentials",
            json={
                "access_key_id": "",
                "secret_access_key": "somesecret",
                "session_token": None,
                "region": "us-east-1",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"
        assert data["recoverable"] is False

    async def test_whitespace_secret_key_returns_400(self, client: AsyncClient) -> None:
        """Whitespace-only secret_access_key returns 400."""
        response = await client.post(
            "/api/credentials",
            json={
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "   ",
                "session_token": None,
                "region": "us-east-1",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"


class TestGetCredentialStatus:
    """Tests for GET /api/credentials/status."""

    async def test_initial_status_is_disconnected(self, client: AsyncClient) -> None:
        """Fresh state returns disconnected status."""
        response = await client.get("/api/credentials/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["status"] == "Disconnected"
        assert data["account_id"] is None

    async def test_status_after_connection(
        self, client: AsyncClient, aws_credentials
    ) -> None:
        """After connecting, status reflects connected state."""
        with mock_aws():
            await client.post(
                "/api/credentials",
                json={
                    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "session_token": None,
                    "region": "us-east-1",
                },
            )
            response = await client.get("/api/credentials/status")
            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is True
            assert data["status"] == "Connected"


class TestDeleteCredentials:
    """Tests for DELETE /api/credentials."""

    async def test_delete_clears_credentials(
        self, client: AsyncClient, aws_credentials
    ) -> None:
        """DELETE returns disconnected status after clearing."""
        with mock_aws():
            # First connect
            await client.post(
                "/api/credentials",
                json={
                    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "session_token": None,
                    "region": "us-east-1",
                },
            )

            # Then disconnect
            response = await client.delete("/api/credentials")
            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is False
            assert data["status"] == "Disconnected"
            assert data["account_id"] is None
            assert data["credential_source"] is None

    async def test_delete_when_already_disconnected(self, client: AsyncClient) -> None:
        """DELETE on already-disconnected state is safe and returns disconnected."""
        response = await client.delete("/api/credentials")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["status"] == "Disconnected"

    async def test_status_after_delete_is_disconnected(
        self, client: AsyncClient, aws_credentials
    ) -> None:
        """GET status after DELETE confirms disconnected state (Req 2.5)."""
        with mock_aws():
            await client.post(
                "/api/credentials",
                json={
                    "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "session_token": None,
                    "region": "us-east-1",
                },
            )
            await client.delete("/api/credentials")

            response = await client.get("/api/credentials/status")
            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is False
            assert data["account_id"] is None
            assert data["credential_source"] is None
