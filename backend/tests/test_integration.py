"""Backend integration tests for CloudSpyglass.

Tests cover:
1. Full scan flow with moto (credential submission → scan → relationship resolution → storage)
2. API endpoint contracts with httpx TestClient
3. File atomicity under concurrent writes

Validates Requirements: 3.2, 4.1, 10.2
"""

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from backend.main import app
from backend.models.resources import Resource
from backend.models.scan import ScanResult
from backend.routes import scan as scan_module
from backend.services.relationship_resolver import RelationshipResolver
from backend.services.scan_storage import ScanStorage


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Create an async httpx test client wrapping the FastAPI app."""
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


@pytest.fixture
def tmp_data_dir():
    """Provide a temporary directory for ScanStorage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(tmp_data_dir: Path) -> ScanStorage:
    """Create a ScanStorage instance pointed at a temp directory."""
    return ScanStorage(data_dir=tmp_data_dir)


def _make_scan_result(account_id: str = "123456789012", num_resources: int = 0) -> ScanResult:
    """Create a valid ScanResult for testing."""
    resources = []
    for i in range(num_resources):
        resources.append(Resource(
            arn=f"arn:aws:ec2:us-east-1:{account_id}:instance/i-{i:012d}",
            resource_type="ec2",
            name=f"instance-{i}",
            region="us-east-1",
            tags={"Name": f"instance-{i}"},
            attributes={"instance_type": "t3.micro", "state": "running"},
        ))
    return ScanResult(
        account_id=account_id,
        scan_timestamp=datetime.now(timezone.utc).isoformat(),
        resources=resources,
        relationships=[],
        failures=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1500,
    )


# ===========================================================================
# Section 1: Full scan flow with moto
# ===========================================================================


class TestFullScanFlowWithMoto:
    """Integration tests for the full scan flow using moto for AWS mocking."""

    async def test_credential_submission_with_sts_validation(self, client: AsyncClient):
        """Test that credential submission validates via mocked STS and returns CredentialStatus."""
        with mock_aws():
            response = await client.post("/api/credentials", json={
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "session_token": None,
                "region": "us-east-1",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is True
            assert data["account_id"] is not None
            assert data["status"] == "Connected"
            assert data["credential_source"] == "ui"

    async def test_scan_trigger_and_completion(self, client: AsyncClient):
        """Test that triggering a scan returns accepted status and completes."""
        with mock_aws():
            # First submit credentials
            await client.post("/api/credentials", json={
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "session_token": None,
                "region": "us-east-1",
            })

            # Trigger scan
            response = await client.post("/api/scan", json={"regions": ["us-east-1"]})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "accepted"
            assert data["started_at"] is not None

            # Wait for background scan to complete (allow up to 30s for moto)
            for _ in range(150):
                await asyncio.sleep(0.2)
                status_resp = await client.get("/api/scan/status")
                status_data = status_resp.json()
                if status_data["status"] in ("completed", "failed"):
                    break

            # The scan should have either completed or failed
            status_resp = await client.get("/api/scan/status")
            final_status = status_resp.json()
            assert final_status["status"] in ("completed", "failed")
            assert final_status["started_at"] is not None

    async def test_relationship_resolution_produces_correct_relationships(self):
        """Test that RelationshipResolver detects network/iam relationships from resources."""
        account_id = "123456789012"
        resources = [
            Resource(
                arn=f"arn:aws:ec2:us-east-1:{account_id}:instance/i-abc123",
                resource_type="ec2",
                name="web-server",
                region="us-east-1",
                tags={"Name": "web-server"},
                iam_role=f"arn:aws:iam::{account_id}:role/WebRole",
                attributes={
                    "vpc_id": "vpc-12345",
                    "subnet_id": "subnet-abcde",
                    "security_groups": ["sg-001"],
                },
            ),
            Resource(
                arn=f"arn:aws:lambda:us-east-1:{account_id}:function:my-func",
                resource_type="lambda",
                name="my-func",
                region="us-east-1",
                tags={},
                iam_role=f"arn:aws:iam::{account_id}:role/LambdaRole",
                attributes={
                    "vpc_id": "vpc-12345",
                    "subnet_ids": ["subnet-abcde"],
                },
            ),
        ]

        resolver = RelationshipResolver(account_id)
        relationships, unresolved = resolver.resolve(resources)

        # Verify network relationships were detected
        network_rels = [r for r in relationships if r.category == "network"]
        assert len(network_rels) > 0

        # EC2 → VPC relationship
        ec2_vpc_rels = [
            r for r in network_rels
            if "instance/i-abc123" in r.source_arn and "vpc/vpc-12345" in r.target_arn
        ]
        assert len(ec2_vpc_rels) == 1
        assert ec2_vpc_rels[0].derived_from == "VpcId"

        # EC2 → Security Group
        ec2_sg_rels = [
            r for r in network_rels
            if "instance/i-abc123" in r.source_arn and "security-group/sg-001" in r.target_arn
        ]
        assert len(ec2_sg_rels) == 1

        # IAM relationships
        iam_rels = [r for r in relationships if r.category == "iam"]
        assert len(iam_rels) == 2  # EC2 and Lambda both have IAM roles

        # Unresolved targets should be generated for referenced ARNs not in scan
        assert len(unresolved) > 0
        for resource in unresolved:
            assert resource.is_unresolved is True

    async def test_scan_result_persisted_to_storage(self, storage: ScanStorage):
        """Test that scan results are persisted to disk via ScanStorage."""
        account_id = "123456789012"
        scan_result = _make_scan_result(account_id, num_resources=3)

        # Save to storage
        await storage.save(account_id, scan_result)

        # Load and verify
        loaded = await storage.load(account_id)
        assert loaded is not None
        assert loaded.account_id == account_id
        assert len(loaded.resources) == 3
        assert loaded.scanned_regions == ["us-east-1"]
        assert loaded.total_scan_duration_ms == 1500


# ===========================================================================
# Section 2: API endpoint contracts with httpx TestClient
# ===========================================================================


class TestAPIEndpointContracts:
    """Tests for API endpoint contracts ensuring response structures match models."""

    async def test_error_response_structure_on_409(self, client: AsyncClient):
        """POST /api/scan returns 409 with proper ErrorResponse when scan is in progress."""
        scan_module._scan_status = scan_module.ScanStatus.in_progress
        scan_module._scan_started_at = "2024-01-01T00:00:00+00:00"

        response = await client.post("/api/scan", json={"regions": ["us-east-1"]})
        assert response.status_code == 409

        data = response.json()
        # Verify ErrorResponse structure (Requirement 14.1)
        assert "error_code" in data
        assert "message" in data
        assert "details" in data
        assert "timestamp" in data
        assert "recoverable" in data

        # Verify field types
        assert isinstance(data["error_code"], str)
        assert isinstance(data["message"], str)
        assert data["details"] is None or isinstance(data["details"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["recoverable"], bool)

        # Verify error_code is UPPER_SNAKE_CASE
        assert data["error_code"] == "SCAN_IN_PROGRESS"
        assert data["recoverable"] is False

    async def test_credential_status_returns_credential_status_model(self, client: AsyncClient):
        """GET /api/credentials/status returns CredentialStatus structure."""
        response = await client.get("/api/credentials/status")
        assert response.status_code == 200

        data = response.json()
        assert "connected" in data
        assert "status" in data
        assert isinstance(data["connected"], bool)
        assert data["status"] in ("Connected", "Disconnected", "Expired")

    async def test_post_credentials_returns_credential_status(self, client: AsyncClient):
        """POST /api/credentials returns CredentialStatus on success."""
        with mock_aws():
            response = await client.post("/api/credentials", json={
                "access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "session_token": None,
                "region": "us-east-1",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["connected"] is True
            assert data["account_id"] is not None
            assert data["status"] == "Connected"
            assert data["credential_source"] in ("ui", "boto3_chain")

    async def test_scan_status_returns_scan_progress_structure(self, client: AsyncClient):
        """GET /api/scan/status returns proper ScanProgress structure."""
        response = await client.get("/api/scan/status")
        assert response.status_code == 200

        data = response.json()
        # Verify ScanProgress fields
        assert "status" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "error_message" in data
        assert "total_resources" in data
        assert "total_regions" in data
        assert "total_failures" in data

        # Initial state should be idle
        assert data["status"] == "idle"
        assert data["started_at"] is None
        assert data["completed_at"] is None

    async def test_diagrams_latest_returns_404_when_no_scan_data(self, client: AsyncClient):
        """GET /api/diagrams/latest returns 404 with ErrorResponse when no scan data exists."""
        response = await client.get("/api/diagrams/latest")
        assert response.status_code == 404

        data = response.json()
        # Verify ErrorResponse structure
        assert data["error_code"] == "NO_SCAN_DATA"
        assert "message" in data
        assert "timestamp" in data
        assert "recoverable" in data
        assert data["recoverable"] is True

    async def test_post_credentials_empty_key_returns_error_response(self, client: AsyncClient):
        """POST /api/credentials with empty access_key_id returns ErrorResponse."""
        response = await client.post("/api/credentials", json={
            "access_key_id": "",
            "secret_access_key": "some-secret",
            "session_token": None,
            "region": "us-east-1",
        })

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"
        assert "message" in data
        assert "timestamp" in data
        assert "recoverable" in data
        assert data["recoverable"] is False

    async def test_post_credentials_whitespace_key_returns_error_response(self, client: AsyncClient):
        """POST /api/credentials with whitespace-only secret returns ErrorResponse."""
        response = await client.post("/api/credentials", json={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "   ",
            "session_token": None,
            "region": "us-east-1",
        })

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_CREDENTIALS"
        assert data["recoverable"] is False

    async def test_error_timestamp_is_iso8601_utc(self, client: AsyncClient):
        """All error responses have a valid ISO 8601 UTC timestamp."""
        scan_module._scan_status = scan_module.ScanStatus.in_progress
        scan_module._scan_started_at = "2024-01-01T00:00:00+00:00"

        response = await client.post("/api/scan", json={})
        data = response.json()

        # The timestamp should parse as a valid ISO 8601 datetime
        ts = data["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None or ts.endswith("Z") or "+" in ts

    async def test_error_message_under_500_chars(self, client: AsyncClient):
        """Error message field is at most 500 characters."""
        response = await client.post("/api/credentials", json={
            "access_key_id": "",
            "secret_access_key": "secret",
            "session_token": None,
            "region": "us-east-1",
        })

        data = response.json()
        assert len(data["message"]) <= 500


# ===========================================================================
# Section 3: File atomicity under concurrent writes
# ===========================================================================


class TestFileAtomicityUnderConcurrentWrites:
    """Tests for ScanStorage file atomicity with concurrent writes."""

    async def test_concurrent_saves_produce_valid_file(self, storage: ScanStorage):
        """Multiple concurrent save() calls for the same account produce a valid final file."""
        account_id = "111222333444"

        # Create multiple distinct scan results
        results = []
        for i in range(10):
            result = ScanResult(
                account_id=account_id,
                scan_timestamp=datetime.now(timezone.utc).isoformat(),
                resources=[
                    Resource(
                        arn=f"arn:aws:ec2:us-east-1:{account_id}:instance/i-{i:012d}",
                        resource_type="ec2",
                        name=f"instance-{i}",
                        region="us-east-1",
                        tags={"version": str(i)},
                        attributes={"instance_type": "t3.micro"},
                    )
                ],
                relationships=[],
                failures=[],
                scanned_regions=["us-east-1"],
                total_scan_duration_ms=i * 100,
            )
            results.append(result)

        # Fire all saves concurrently
        await asyncio.gather(*[
            storage.save(account_id, result)
            for result in results
        ])

        # Verify the final file is valid and complete (no partial writes)
        loaded = await storage.load(account_id)
        assert loaded is not None
        assert loaded.account_id == account_id
        assert len(loaded.resources) == 1  # Each result has 1 resource
        assert loaded.scanned_regions == ["us-east-1"]

        # The loaded result should be one of the written results (last writer wins)
        assert loaded.total_scan_duration_ms in [i * 100 for i in range(10)]

    async def test_exactly_one_file_per_account(self, tmp_data_dir: Path):
        """Concurrent writes for the same account_id result in exactly one file."""
        storage = ScanStorage(data_dir=tmp_data_dir)
        account_id = "999888777666"

        results = [_make_scan_result(account_id, num_resources=i + 1) for i in range(5)]

        await asyncio.gather(*[
            storage.save(account_id, result)
            for result in results
        ])

        # Check that only one JSON file exists for this account
        json_files = list(tmp_data_dir.glob(f"{account_id}.json"))
        assert len(json_files) == 1

        # Verify no temp files are left behind
        tmp_files = list(tmp_data_dir.glob(f".{account_id}_*.tmp"))
        assert len(tmp_files) == 0

    async def test_concurrent_saves_different_accounts(self, tmp_data_dir: Path):
        """Concurrent writes for different accounts each produce their own valid file."""
        storage = ScanStorage(data_dir=tmp_data_dir)
        account_ids = [f"{i:012d}" for i in range(5)]

        results = [_make_scan_result(acct_id, num_resources=2) for acct_id in account_ids]

        await asyncio.gather(*[
            storage.save(result.account_id, result)
            for result in results
        ])

        # Verify each account has exactly one file
        for acct_id in account_ids:
            json_files = list(tmp_data_dir.glob(f"{acct_id}.json"))
            assert len(json_files) == 1

            loaded = await storage.load(acct_id)
            assert loaded is not None
            assert loaded.account_id == acct_id
            assert len(loaded.resources) == 2

    async def test_file_not_corrupted_under_rapid_writes(self, storage: ScanStorage):
        """Rapidly writing different data sizes doesn't corrupt the stored file."""
        account_id = "555666777888"

        # Write results with increasing sizes
        for size in [1, 10, 50, 5, 100, 2]:
            result = _make_scan_result(account_id, num_resources=size)
            await storage.save(account_id, result)

            # After each write, verify file is still valid
            loaded = await storage.load(account_id)
            assert loaded is not None
            assert loaded.account_id == account_id
            assert len(loaded.resources) == size

    async def test_concurrent_mixed_size_writes(self, tmp_data_dir: Path):
        """Concurrent writes of varying sizes all result in valid, non-corrupted data."""
        storage = ScanStorage(data_dir=tmp_data_dir)
        account_id = "444333222111"

        # Create results with very different sizes to stress atomic writes
        sizes = [1, 50, 5, 100, 10, 200, 3]
        results = [_make_scan_result(account_id, num_resources=s) for s in sizes]

        await asyncio.gather(*[
            storage.save(account_id, result)
            for result in results
        ])

        # Final file must be valid
        loaded = await storage.load(account_id)
        assert loaded is not None
        assert loaded.account_id == account_id
        # The number of resources should match one of the written sizes
        assert len(loaded.resources) in sizes
