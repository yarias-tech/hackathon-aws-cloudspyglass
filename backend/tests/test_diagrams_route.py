"""Integration tests for the /api/diagrams/latest endpoint.

Tests verify:
1. Response includes `hierarchy` field with correct structure
2. Hierarchy is null (404) when no scan data exists
3. Backward compatibility: existing fields remain unchanged

Validates: Requirements 6.5
"""

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.models.resources import Relationship, Resource
from backend.models.scan import ScanResult
from backend.routes import scan as scan_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Create an async httpx test client wrapping the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_scan_state():
    """Reset scan module state between tests."""
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


def _make_scan_result_with_vpc_resources() -> ScanResult:
    """Create a ScanResult with EC2 in a VPC/subnet for hierarchy testing."""
    account_id = "123456789012"
    return ScanResult(
        account_id=account_id,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
        resources=[
            Resource(
                arn=f"arn:aws:ec2:us-east-1:{account_id}:vpc/vpc-abc123",
                resource_type="vpc",
                name="my-vpc",
                region="us-east-1",
                tags={"Name": "my-vpc"},
                attributes={"cidr_block": "10.0.0.0/16"},
            ),
            Resource(
                arn=f"arn:aws:ec2:us-east-1:{account_id}:subnet/subnet-pub1",
                resource_type="subnet",
                name="public-subnet-1",
                region="us-east-1",
                tags={"Name": "public-subnet-1"},
                attributes={
                    "vpc_id": "vpc-abc123",
                    "availability_zone": "us-east-1a",
                    "cidr_block": "10.0.1.0/24",
                },
            ),
            Resource(
                arn=f"arn:aws:ec2:us-east-1:{account_id}:instance/i-0001",
                resource_type="ec2",
                name="web-server",
                region="us-east-1",
                tags={"Name": "web-server"},
                attributes={
                    "instance_type": "t3.micro",
                    "state": "running",
                    "vpc_id": "vpc-abc123",
                    "subnet_id": "subnet-pub1",
                    "availability_zone": "us-east-1a",
                },
            ),
        ],
        relationships=[
            Relationship(
                source_arn=f"arn:aws:ec2:us-east-1:{account_id}:instance/i-0001",
                target_arn=f"arn:aws:ec2:us-east-1:{account_id}:vpc/vpc-abc123",
                category="network",
                derived_from="VpcId",
            ),
        ],
        failures=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1200,
    )


# ===========================================================================
# Test: Response includes hierarchy field
# ===========================================================================


class TestDiagramsLatestHierarchyField:
    """Tests that /api/diagrams/latest response includes the hierarchy field."""

    async def test_response_includes_hierarchy_field(self, client: AsyncClient):
        """GET /api/diagrams/latest includes a non-null hierarchy field when scan data exists."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        assert "hierarchy" in data
        assert data["hierarchy"] is not None

    async def test_hierarchy_has_correct_structure(self, client: AsyncClient):
        """The hierarchy field has containers, root_id, and boundary_services."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        hierarchy = response.json()["hierarchy"]
        assert "containers" in hierarchy
        assert "root_id" in hierarchy
        assert "boundary_services" in hierarchy

        # containers should be a non-empty list
        assert isinstance(hierarchy["containers"], list)
        assert len(hierarchy["containers"]) > 0

        # root_id should be a string
        assert isinstance(hierarchy["root_id"], str)

        # boundary_services should be a list
        assert isinstance(hierarchy["boundary_services"], list)

    async def test_hierarchy_containers_have_required_metadata(self, client: AsyncClient):
        """Each container in hierarchy has the required ContainerMetadata fields."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        containers = response.json()["hierarchy"]["containers"]
        required_fields = {"id", "name", "type", "parent_id", "icon_key", "resources", "children"}

        for container in containers:
            for field in required_fields:
                assert field in container, f"Missing field '{field}' in container {container.get('id')}"

            # type must be one of the valid container types
            assert container["type"] in ("cloud", "account", "region", "vpc", "az", "subnet")


# ===========================================================================
# Test: Hierarchy is null when no scan data exists
# ===========================================================================


class TestDiagramsLatestNoScanData:
    """Tests that /api/diagrams/latest returns 404 when no scan data exists."""

    async def test_returns_404_when_no_scan_data(self, client: AsyncClient):
        """GET /api/diagrams/latest returns 404 with NO_SCAN_DATA error when scan is None."""
        # _last_scan_result is None by default (from reset_scan_state fixture)
        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 404

        data = response.json()
        assert data["error_code"] == "NO_SCAN_DATA"
        assert "message" in data
        assert data["recoverable"] is True


# ===========================================================================
# Test: Backward compatibility — existing fields unchanged
# ===========================================================================


class TestDiagramsLatestBackwardCompatibility:
    """Tests that existing DiagramData fields remain present and correctly populated."""

    async def test_existing_fields_present(self, client: AsyncClient):
        """GET /api/diagrams/latest still returns all original DiagramData fields."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()

        # All original fields must be present
        assert "nodes" in data
        assert "edges" in data
        assert "account_id" in data
        assert "scan_timestamp" in data
        assert "total_resources" in data
        assert "scanned_regions" in data
        assert "failures" in data

    async def test_nodes_populated_correctly(self, client: AsyncClient):
        """Nodes field contains expected resources with correct structure."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        nodes = data["nodes"]

        assert isinstance(nodes, list)
        assert len(nodes) > 0

        # Each node should have the required DiagramNode fields
        for node in nodes:
            assert "id" in node
            assert "resource_type" in node
            assert "name" in node
            assert "region" in node
            assert "icon_url" in node

    async def test_account_id_matches_scan_result(self, client: AsyncClient):
        """account_id field matches what was set in the scan result."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        assert data["account_id"] == "123456789012"

    async def test_scanned_regions_matches_scan_result(self, client: AsyncClient):
        """scanned_regions field matches the scan result."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        assert data["scanned_regions"] == ["us-east-1"]

    async def test_total_resources_matches_node_count(self, client: AsyncClient):
        """total_resources reflects the number of discovered resources."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        # total_resources should be the count from the scan result
        assert isinstance(data["total_resources"], int)
        assert data["total_resources"] > 0

    async def test_failures_field_is_empty_list(self, client: AsyncClient):
        """failures field is an empty list when no failures in scan."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        assert data["failures"] == []

    async def test_edges_field_present_and_correct_structure(self, client: AsyncClient):
        """edges field contains relationships with correct DiagramEdge structure."""
        scan_module._last_scan_result = _make_scan_result_with_vpc_resources()

        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 200

        data = response.json()
        edges = data["edges"]

        assert isinstance(edges, list)
        assert len(edges) > 0

        # Each edge should have the required DiagramEdge fields
        for edge in edges:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge
            assert "category" in edge
            assert "derived_from" in edge
