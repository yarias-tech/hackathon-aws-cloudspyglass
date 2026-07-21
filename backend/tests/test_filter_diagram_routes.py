"""Unit tests for the filter and diagram API routes."""

import json
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
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
            Resource(
                arn="arn:aws:s3:::my-bucket",
                resource_type="s3",
                name="my-bucket",
                region="us-east-1",
                tags={"env": "dev"},
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


class TestGetTagSuggestions:
    """Tests for GET /api/tags/suggestions."""

    async def test_no_scan_data_returns_404(self, client: AsyncClient) -> None:
        """When no scan data exists, returns 404 with NO_SCAN_DATA error."""
        with patch("backend.routes.filters.get_last_scan_result", return_value=None):
            response = await client.get("/api/tags/suggestions?prefix=env")
            assert response.status_code == 404
            data = response.json()
            assert data["error_code"] == "NO_SCAN_DATA"
            assert data["recoverable"] is True

    async def test_returns_suggestions_with_prefix(self, client: AsyncClient) -> None:
        """Returns matching tag suggestions when scan data exists."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.filters.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get("/api/tags/suggestions?prefix=env")
            assert response.status_code == 200
            data = response.json()
            assert len(data) > 0
            # "env" key matches — "prod" appears on 2 resources, "dev" on 1
            keys = [item["key"] for item in data]
            assert "env" in keys

    async def test_returns_suggestions_without_prefix(
        self, client: AsyncClient
    ) -> None:
        """Empty prefix returns all tag suggestions."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.filters.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get("/api/tags/suggestions")
            assert response.status_code == 200
            data = response.json()
            # Should have entries for env:prod, env:dev, team:backend, team:data
            assert len(data) == 4

    async def test_suggestions_ordered_by_frequency(
        self, client: AsyncClient
    ) -> None:
        """Suggestions are ordered by descending frequency."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.filters.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get("/api/tags/suggestions?prefix=env")
            assert response.status_code == 200
            data = response.json()
            # env:prod appears on 2 resources, env:dev on 1
            assert data[0]["value"] == "prod"
            assert data[0]["count"] == 2
            assert data[1]["value"] == "dev"
            assert data[1]["count"] == 1


class TestGetLatestDiagram:
    """Tests for GET /api/diagrams/latest."""

    async def test_no_scan_data_returns_404(self, client: AsyncClient) -> None:
        """When no scan data exists, returns 404 with NO_SCAN_DATA error."""
        with patch("backend.routes.diagrams.get_last_scan_result", return_value=None):
            response = await client.get("/api/diagrams/latest")
            assert response.status_code == 404
            data = response.json()
            assert data["error_code"] == "NO_SCAN_DATA"

    async def test_returns_diagram_data(self, client: AsyncClient) -> None:
        """Returns full diagram data when scan result exists."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get("/api/diagrams/latest")
            assert response.status_code == 200
            data = response.json()
            assert data["account_id"] == "123456789012"
            assert data["total_resources"] == 3
            assert len(data["nodes"]) == 3
            assert len(data["edges"]) == 1
            assert data["scanned_regions"] == ["us-east-1"]


class TestGetFilteredDiagram:
    """Tests for GET /api/diagrams/latest/filtered."""

    async def test_no_scan_data_returns_404(self, client: AsyncClient) -> None:
        """When no scan data exists, returns 404."""
        with patch("backend.routes.diagrams.get_last_scan_result", return_value=None):
            response = await client.get("/api/diagrams/latest/filtered")
            assert response.status_code == 404

    async def test_no_filters_returns_all(self, client: AsyncClient) -> None:
        """No filters returns full unfiltered result."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get("/api/diagrams/latest/filtered")
            assert response.status_code == 200
            data = response.json()
            assert data["filtered_count"] == 3
            assert data["total_count"] == 3

    async def test_tag_filter_reduces_results(self, client: AsyncClient) -> None:
        """Tag filters narrow down the results (AND logic)."""
        scan_result = _make_scan_result()
        tag_filters_json = json.dumps([{"key": "env", "value": "prod"}])
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get(
                f"/api/diagrams/latest/filtered?tag_filters={tag_filters_json}"
            )
            assert response.status_code == 200
            data = response.json()
            # Only ec2 and lambda have env:prod
            assert data["filtered_count"] == 2
            assert data["total_count"] == 3

    async def test_type_filter_reduces_results(self, client: AsyncClient) -> None:
        """Type filters narrow down the results (OR logic)."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get(
                "/api/diagrams/latest/filtered?type_filters=ec2,s3"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["filtered_count"] == 2
            assert data["total_count"] == 3

    async def test_invalid_tag_filters_json_returns_400(
        self, client: AsyncClient
    ) -> None:
        """Invalid JSON in tag_filters returns 400."""
        scan_result = _make_scan_result()
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get(
                "/api/diagrams/latest/filtered?tag_filters=not-json"
            )
            assert response.status_code == 400
            data = response.json()
            assert data["error_code"] == "INVALID_FILTER"

    async def test_tag_filters_not_array_returns_400(
        self, client: AsyncClient
    ) -> None:
        """tag_filters that isn't an array returns 400."""
        scan_result = _make_scan_result()
        tag_filters_json = json.dumps({"key": "env", "value": "prod"})
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get(
                f"/api/diagrams/latest/filtered?tag_filters={tag_filters_json}"
            )
            assert response.status_code == 400
            data = response.json()
            assert data["error_code"] == "INVALID_FILTER"

    async def test_combined_filters(self, client: AsyncClient) -> None:
        """Combined tag + type filters produce intersection."""
        scan_result = _make_scan_result()
        tag_filters_json = json.dumps([{"key": "env", "value": "prod"}])
        with patch(
            "backend.routes.diagrams.get_last_scan_result", return_value=scan_result
        ):
            response = await client.get(
                f"/api/diagrams/latest/filtered?tag_filters={tag_filters_json}&type_filters=ec2"
            )
            assert response.status_code == 200
            data = response.json()
            # Only ec2 has env:prod AND is type ec2
            assert data["filtered_count"] == 1
            assert data["total_count"] == 3
