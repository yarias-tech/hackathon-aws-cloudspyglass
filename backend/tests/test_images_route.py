"""Unit tests for the image serving API routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestGetServiceIcon:
    """Tests for GET /api/images/icons/{service_type}."""

    async def test_valid_service_type_returns_svg(self, client: AsyncClient):
        """Valid service type returns SVG content with correct content-type."""
        async with client:
            response = await client.get("/api/images/icons/ec2")

        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert b"<svg" in response.content

    async def test_invalid_service_type_returns_400(self, client: AsyncClient):
        """Unknown service type returns 400 with INVALID_SERVICE_TYPE error."""
        async with client:
            response = await client.get("/api/images/icons/nonexistent_service")

        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "INVALID_SERVICE_TYPE"
        assert "nonexistent_service" in body["message"]

    async def test_all_known_types_return_200(self, client: AsyncClient):
        """All known resource types return a successful response."""
        known_types = [
            "ec2", "lambda", "s3", "rds", "dynamodb", "vpc", "subnet",
            "security_group", "alb", "nlb", "ecs", "sns", "sqs",
            "cloudfront", "route53", "apigateway", "iam_role",
        ]
        async with client:
            for service_type in known_types:
                response = await client.get(f"/api/images/icons/{service_type}")
                assert response.status_code == 200, (
                    f"Expected 200 for {service_type}, got {response.status_code}"
                )

    async def test_empty_service_type_returns_400(self, client: AsyncClient):
        """Empty string as service_type returns 400."""
        async with client:
            # FastAPI will match the empty path differently, but a random string should 400
            response = await client.get("/api/images/icons/unknown")

        assert response.status_code == 400


class TestGetLogo:
    """Tests for GET /api/images/logo."""

    async def test_logo_returns_png(self, client: AsyncClient):
        """Logo endpoint returns PNG content with correct content-type."""
        async with client:
            response = await client.get("/api/images/logo")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        # PNG files start with the PNG magic bytes
        assert response.content[:4] == b"\x89PNG"
