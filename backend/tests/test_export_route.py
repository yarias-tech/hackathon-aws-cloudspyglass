"""Unit tests for the export API route."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.export import ExportFormat, ExportResult
from backend.models.resources import Relationship, Resource
from backend.models.scan import ScanResult


def _make_scan_result() -> ScanResult:
    """Create a minimal ScanResult for testing."""
    return ScanResult(
        account_id="123456789012",
        scan_timestamp="2024-01-15T10:00:00Z",
        resources=[
            Resource(
                arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc",
                resource_type="ec2",
                name="web-server",
                region="us-east-1",
                tags={"env": "prod", "team": "backend"},
            ),
            Resource(
                arn="arn:aws:lambda:us-east-1:123456789012:function:my-func",
                resource_type="lambda",
                name="my-func",
                region="us-east-1",
                tags={"env": "prod", "team": "data"},
            ),
        ],
        relationships=[
            Relationship(
                source_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc",
                target_arn="arn:aws:lambda:us-east-1:123456789012:function:my-func",
                category="event",
                derived_from="event_source_mapping",
            ),
        ],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=5000,
    )


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestExportRoute:
    """Tests for POST /api/export."""

    async def test_no_scan_data_returns_404(self, client: AsyncClient) -> None:
        """When no scan data exists, returns 404 with NO_SCAN_DATA error."""
        with patch("backend.routes.export.get_last_scan_result", return_value=None):
            response = await client.post(
                "/api/export", json={"format": "svg"}
            )
            assert response.status_code == 404
            data = response.json()
            assert data["error_code"] == "NO_SCAN_DATA"
            assert data["recoverable"] is True

    async def test_export_svg_success(self, client: AsyncClient) -> None:
        """Successfully exports SVG when scan data exists."""
        scan_result = _make_scan_result()
        mock_result = ExportResult(
            filename="123456789012_20240115_100000.svg",
            format=ExportFormat.SVG,
            size_bytes=1024,
            path="/workspace/exports/123456789012_20240115_100000.svg",
        )

        with patch(
            "backend.routes.export.get_last_scan_result", return_value=scan_result
        ), patch(
            "backend.routes.export._export_service.export",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await client.post(
                "/api/export", json={"format": "svg"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filename"] == "123456789012_20240115_100000.svg"
            assert data["format"] == "svg"
            assert data["size_bytes"] == 1024

    async def test_export_with_filters(self, client: AsyncClient) -> None:
        """Export with filters passes them through to the service."""
        scan_result = _make_scan_result()
        mock_result = ExportResult(
            filename="123456789012_20240115_100000.png",
            format=ExportFormat.PNG,
            size_bytes=2048,
            path="/workspace/exports/123456789012_20240115_100000.png",
        )

        with patch(
            "backend.routes.export.get_last_scan_result", return_value=scan_result
        ), patch(
            "backend.routes.export._export_service.export",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_export:
            response = await client.post(
                "/api/export",
                json={
                    "format": "png",
                    "filters": {
                        "tag_filters": [{"key": "env", "value": "prod"}],
                        "type_filters": ["ec2"],
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["format"] == "png"
            # Verify export was called with filters
            mock_export.assert_called_once()
            call_kwargs = mock_export.call_args
            assert call_kwargs.kwargs["filters"] is not None

    async def test_export_invalid_format_returns_422(self, client: AsyncClient) -> None:
        """Invalid export format returns 422 validation error."""
        with patch(
            "backend.routes.export.get_last_scan_result",
            return_value=_make_scan_result(),
        ):
            response = await client.post(
                "/api/export", json={"format": "docx"}
            )
            assert response.status_code == 422
