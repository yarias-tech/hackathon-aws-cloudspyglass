"""Property-based tests for partial region failure handling.

**Validates: Requirements 3.5**

Property 6: Partial region failure handling
- Test that successful regions produce resources and failed regions produce failure entries.
- IF scanning fails for one or more regions, THEN THE Scanner SHALL return successful
  results from other regions along with a failures list where each entry includes the
  region name, the resource type that failed, the error message, and a timestamp.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from backend.models.resources import Resource
from backend.services.scanner import Scanner


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

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


@st.composite
def partial_failure_strategy(draw):
    """Generate a partition of regions into success and failure sets.

    Ensures at least one region succeeds and at least one fails.
    """
    # Pick between 2 and 6 regions total
    all_regions = draw(
        st.lists(
            st.sampled_from(VALID_AWS_REGIONS),
            min_size=2,
            max_size=6,
            unique=True,
        )
    )
    # Split: at least 1 success and at least 1 failure
    split_index = draw(st.integers(min_value=1, max_value=len(all_regions) - 1))
    success_regions = all_regions[:split_index]
    fail_regions = all_regions[split_index:]
    return success_regions, fail_regions


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
# Helpers
# ---------------------------------------------------------------------------


def make_fake_resource(region: str, resource_type: str) -> Resource:
    """Create a fake Resource for a given region and type."""
    return Resource(
        arn=f"arn:aws:ec2:{region}:123456789012:instance/i-fake-{region}-{resource_type}",
        resource_type=resource_type,
        name=f"fake-{resource_type}-{region}",
        region=region,
        tags={},
    )


def is_valid_iso8601(timestamp_str: str) -> bool:
    """Check if a string is a valid ISO 8601 timestamp."""
    try:
        datetime.fromisoformat(timestamp_str)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Property: Partial failure returns resources from successes and failures list
# ---------------------------------------------------------------------------


class TestPartialRegionFailureHandling:
    """When some regions fail and others succeed, Scanner returns both resources and failures."""

    @given(data=partial_failure_strategy())
    @settings(max_examples=50, deadline=None)
    async def test_successful_regions_produce_resources_and_failed_regions_produce_failures(
        self, data: tuple[list[str], list[str]]
    ) -> None:
        """For any partition of regions into success/fail sets:
        - scanned_regions contains exactly the success regions
        - failures contains entries for each failed region with region, resource_type,
          error_message, and a valid ISO 8601 timestamp
        - resources are returned from successful regions

        We patch _scan_region to simulate whole-region failures (which cause a region
        to NOT appear in scanned_regions) and successful regions (which return resources).
        """
        success_regions, fail_regions = data
        all_regions = success_regions + fail_regions

        with mock_aws():
            session = boto3.Session(region_name="us-east-1")
            cred_mgr = AsyncMock()
            cred_mgr.get_boto3_session = AsyncMock(return_value=session)

            scanner = Scanner(cred_mgr)

            # Patch _scan_region to simulate region-level behavior:
            # - Success regions return resources
            # - Fail regions raise an exception (simulating a region-level failure)
            original_scan_region = scanner._scan_region

            async def mock_scan_region(region, account_id):
                if region in fail_regions:
                    raise RuntimeError(f"Simulated total failure in {region}")
                # For success regions, return some fake resources and no failures
                resources = [make_fake_resource(region, "ec2")]
                return resources, []

            with patch.object(
                scanner, "_scan_region", side_effect=mock_scan_region
            ), patch.object(
                scanner, "_scan_global_resources", return_value=([], [])
            ):
                result = await scanner.scan(regions=all_regions)

            # 1. scanned_regions contains exactly the success regions
            assert set(result.scanned_regions) == set(success_regions), (
                f"Expected scanned_regions={set(success_regions)}, "
                f"got {set(result.scanned_regions)}"
            )

            # 2. All resources come from success regions only
            for resource in result.resources:
                assert resource.region in success_regions, (
                    f"Resource from region '{resource.region}' should not be present; "
                    f"only success regions {success_regions} should produce resources."
                )

            # 3. There should be resources from successful regions
            assert len(result.resources) == len(success_regions), (
                f"Expected {len(success_regions)} resources (one per success region), "
                f"got {len(result.resources)}"
            )

            # 4. failures list contains entries for each failed region
            failed_region_names_in_result = {f.region for f in result.failures}
            for region in fail_regions:
                assert region in failed_region_names_in_result, (
                    f"Expected failure entry for region '{region}' but it's missing. "
                    f"Failures contain regions: {failed_region_names_in_result}"
                )

            # 5. Each failure entry has required fields with valid values
            for failure in result.failures:
                if failure.region in fail_regions:
                    # Region name is present and matches a fail region
                    assert failure.region in fail_regions, (
                        f"Failure region '{failure.region}' not in expected fail regions"
                    )
                    # resource_type is present (scanner uses "all" for region-level failures)
                    assert failure.resource_type != "", "Failure resource_type must not be empty"
                    # error_message is present and non-empty
                    assert failure.error_message != "", "Failure error_message must not be empty"
                    assert len(failure.error_message) > 0
                    # timestamp is valid ISO 8601
                    assert is_valid_iso8601(failure.timestamp), (
                        f"Failure timestamp '{failure.timestamp}' is not valid ISO 8601"
                    )
