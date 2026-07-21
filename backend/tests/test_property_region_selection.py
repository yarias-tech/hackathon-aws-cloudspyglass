"""Property-based tests for region selection scan targeting.

**Validates: Requirements 3.1**

Property 4: Region selection scan targeting
- For any subset of valid AWS region codes (including the empty set),
  the Scanner SHALL target exactly those regions for scanning; if the
  subset is empty, the Scanner SHALL discover and target all enabled
  regions.
"""

import os
from unittest.mock import AsyncMock, patch

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from backend.services.scanner import Scanner


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid AWS region codes (representative subset for testing)
VALID_AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-west-2",
    "eu-central-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
]

# Strategy: non-empty subsets of valid AWS region codes
non_empty_region_subset_strategy = st.lists(
    st.sampled_from(VALID_AWS_REGIONS),
    min_size=1,
    max_size=5,
    unique=True,
)

# Strategy: empty regions (None or empty list)
empty_region_strategy = st.one_of(
    st.none(),
    st.just([]),
)


# ---------------------------------------------------------------------------
# Setup: mock AWS env for moto
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def aws_env():
    """Set up mock AWS environment variables for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield


# ---------------------------------------------------------------------------
# Property: Specified regions are targeted exactly
# ---------------------------------------------------------------------------

class TestSpecifiedRegionsTargetedExactly:
    """When specific regions are provided, Scanner targets EXACTLY those regions."""

    @given(regions=non_empty_region_subset_strategy)
    @settings(max_examples=50, deadline=None)
    async def test_scanner_targets_exactly_specified_regions(
        self, regions: list[str]
    ) -> None:
        """For any non-empty subset of valid regions, the Scanner scans exactly those regions.

        The scanned_regions in the ScanResult should be exactly the set of regions
        that were specified (since we stub resource fetching to succeed).
        """
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)

            # Patch _fetch_resources to return empty list (fast) and
            # _scan_global_resources to skip global scanning
            with patch.object(
                scanner, "_fetch_resources", return_value=[]
            ), patch.object(
                scanner, "_scan_global_resources", return_value=([], [])
            ):
                result = await scanner.scan(regions=regions)

            # The scanned_regions should be exactly the specified regions
            assert set(result.scanned_regions) == set(regions), (
                f"Expected scanned_regions={set(regions)}, "
                f"got {set(result.scanned_regions)}"
            )


# ---------------------------------------------------------------------------
# Property: Empty/None regions discovers all enabled regions
# ---------------------------------------------------------------------------

class TestEmptyRegionsDiscoversAll:
    """When regions is None or empty, Scanner discovers all enabled regions."""

    @given(regions=empty_region_strategy)
    @settings(max_examples=10, deadline=None)
    async def test_scanner_discovers_all_regions_when_empty(
        self, regions: list[str] | None
    ) -> None:
        """When no regions are specified, Scanner discovers all enabled regions.

        The scanned_regions should match the regions returned by EC2 DescribeRegions.
        """
        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            # Determine expected regions from EC2 DescribeRegions
            ec2 = session.client("ec2", region_name="us-east-1")
            describe_resp = ec2.describe_regions(
                Filters=[{
                    "Name": "opt-in-status",
                    "Values": ["opt-in-not-required", "opted-in"],
                }]
            )
            expected_regions = {
                r["RegionName"] for r in describe_resp.get("Regions", [])
            }

            scanner = Scanner(cred_mgr)

            # Patch _fetch_resources to return empty list (fast) and
            # _scan_global_resources to skip global scanning
            with patch.object(
                scanner, "_fetch_resources", return_value=[]
            ), patch.object(
                scanner, "_scan_global_resources", return_value=([], [])
            ):
                result = await scanner.scan(regions=regions)

            # The scanned_regions should match discovered regions
            assert set(result.scanned_regions) == expected_regions, (
                f"Expected discovered regions={expected_regions}, "
                f"got scanned_regions={set(result.scanned_regions)}"
            )
