"""Property-based tests for write failure preservation.

**Validates: Requirements 10.5**

Property 23: Write failure preserves previous file
- IF writing the Scan_Result file fails, THEN the previously saved file
  SHALL remain unchanged and loadable with its original content.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.exceptions import CloudSpyglassError
from backend.models.resources import Relationship, Resource
from backend.models.scan import RegionFailure, ScanResult
from backend.services.scan_storage import ScanStorage


# ---------------------------------------------------------------------------
# Strategies (reused from existing property tests)
# ---------------------------------------------------------------------------

# Valid AWS account IDs: exactly 12 digits
account_id_strategy = st.from_regex(r"[0-9]{12}", fullmatch=True)

# ISO 8601 timestamps
iso_timestamp_strategy = st.from_regex(
    r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z",
    fullmatch=True,
)

# Valid AWS region codes
region_strategy = st.sampled_from([
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-southeast-1", "ap-northeast-1", "sa-east-1",
])

# Supported resource types
resource_type_strategy = st.sampled_from([
    "ec2", "s3", "lambda", "rds", "vpc", "subnet",
    "security_group", "alb", "nlb", "ecs", "sns", "sqs",
    "dynamodb", "cloudfront", "route53", "apigateway", "iam_role",
])

# Relationship categories
category_strategy = st.sampled_from(["network", "iam", "event", "data"])

# Tag key/value strategies
tag_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=50,
)
tag_value_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_ ."),
    min_size=0,
    max_size=100,
)

# Simple attribute values
attribute_value_strategy = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)


@st.composite
def resource_strategy(draw: st.DrawFn) -> Resource:
    """Generate a valid Resource with random but well-formed data."""
    acct = draw(account_id_strategy)
    region = draw(region_strategy)
    rtype = draw(resource_type_strategy)
    name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=1,
        max_size=30,
    ))
    arn = f"arn:aws:{rtype}:{region}:{acct}:{name}"

    tags = draw(st.dictionaries(
        keys=tag_key_strategy,
        values=tag_value_strategy,
        min_size=0,
        max_size=3,
    ))

    return Resource(
        arn=arn,
        resource_type=rtype,
        name=name,
        region=region,
        tags=tags,
        creation_date=draw(st.one_of(st.none(), iso_timestamp_strategy)),
        iam_role=draw(st.one_of(st.none(), st.just(f"arn:aws:iam::{acct}:role/{name}-role"))),
        attributes=draw(st.dictionaries(
            keys=tag_key_strategy,
            values=attribute_value_strategy,
            min_size=0,
            max_size=2,
        )),
        is_external=draw(st.booleans()),
        is_unresolved=draw(st.booleans()),
    )


@st.composite
def relationship_strategy(draw: st.DrawFn) -> Relationship:
    """Generate a valid Relationship."""
    acct = draw(account_id_strategy)
    region = draw(region_strategy)
    source_type = draw(resource_type_strategy)
    target_type = draw(resource_type_strategy)

    return Relationship(
        source_arn=f"arn:aws:{source_type}:{region}:{acct}:src-{draw(st.integers(1, 9999))}",
        target_arn=f"arn:aws:{target_type}:{region}:{acct}:tgt-{draw(st.integers(1, 9999))}",
        category=draw(category_strategy),
        derived_from=draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._"),
            min_size=1,
            max_size=30,
        )),
    )


@st.composite
def scan_result_strategy(draw: st.DrawFn, account_id: str | None = None) -> ScanResult:
    """Generate a valid ScanResult, optionally fixing the account_id."""
    acct = account_id if account_id is not None else draw(account_id_strategy)
    resources = draw(st.lists(resource_strategy(), min_size=0, max_size=5))
    relationships = draw(st.lists(relationship_strategy(), min_size=0, max_size=3))
    scanned_regions = draw(st.lists(region_strategy, min_size=1, max_size=3))

    return ScanResult(
        account_id=acct,
        scan_timestamp=draw(iso_timestamp_strategy),
        resources=resources,
        relationships=relationships,
        failures=[],
        scanned_regions=scanned_regions,
        total_scan_duration_ms=draw(st.integers(min_value=0, max_value=600_000)),
    )


# Strategy: two distinct ScanResults for the same account (initial + attempted update)
@st.composite
def write_failure_scenario_strategy(draw: st.DrawFn) -> tuple[str, ScanResult, ScanResult]:
    """Generate an account_id with two distinct ScanResults: original and failed update."""
    acct = draw(account_id_strategy)
    original = draw(scan_result_strategy(account_id=acct))
    update = draw(scan_result_strategy(account_id=acct))
    return acct, original, update


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_storage() -> tuple[ScanStorage, Path]:
    """Create a ScanStorage with a fresh temporary directory."""
    tmp_dir = Path(tempfile.mkdtemp())
    data_dir = tmp_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return ScanStorage(data_dir=data_dir), data_dir


# ---------------------------------------------------------------------------
# Property 23: Write failure preserves previous file
# ---------------------------------------------------------------------------

class TestWriteFailurePreservation:
    """Failed writes leave the previous file unchanged and loadable."""

    @given(data=write_failure_scenario_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_mkstemp_failure_preserves_previous_file(
        self, data: tuple[str, ScanResult, ScanResult]
    ) -> None:
        """When tempfile.mkstemp fails (e.g., disk full, permission error),
        the previously saved file remains unchanged and loadable.

        **Validates: Requirements 10.5**
        """
        account_id, original, update = data
        storage, data_dir = _make_storage()

        # Save the original successfully
        await storage.save(account_id, original)

        # Attempt a second save that fails at mkstemp
        with patch("tempfile.mkstemp", side_effect=OSError("Simulated disk full")):
            with pytest.raises(CloudSpyglassError):
                await storage.save(account_id, update)

        # Original file must still be intact and loadable
        loaded = await storage.load(account_id)
        assert loaded is not None, "Previous file should still exist after failed write"
        assert loaded.model_dump() == original.model_dump()

    @given(data=write_failure_scenario_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_fdopen_write_failure_preserves_previous_file(
        self, data: tuple[str, ScanResult, ScanResult]
    ) -> None:
        """When writing to the temp file fails (e.g., disk full during write),
        the previously saved file remains unchanged and loadable.

        **Validates: Requirements 10.5**
        """
        account_id, original, update = data
        storage, data_dir = _make_storage()

        # Save the original successfully
        await storage.save(account_id, original)

        # Attempt a second save that fails during os.fdopen/write
        with patch("os.fdopen", side_effect=OSError("Simulated write failure")):
            with pytest.raises(CloudSpyglassError):
                await storage.save(account_id, update)

        # Original file must still be intact and loadable
        loaded = await storage.load(account_id)
        assert loaded is not None, "Previous file should still exist after failed write"
        assert loaded.model_dump() == original.model_dump()

    @given(data=write_failure_scenario_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_replace_failure_preserves_previous_file(
        self, data: tuple[str, ScanResult, ScanResult]
    ) -> None:
        """When os.replace fails (e.g., cross-device link error),
        the previously saved file remains unchanged and loadable.

        **Validates: Requirements 10.5**
        """
        account_id, original, update = data
        storage, data_dir = _make_storage()

        # Save the original successfully
        await storage.save(account_id, original)

        # Attempt a second save that fails at os.replace
        with patch("os.replace", side_effect=OSError("Simulated replace failure")):
            with pytest.raises(CloudSpyglassError):
                await storage.save(account_id, update)

        # Original file must still be intact and loadable
        loaded = await storage.load(account_id)
        assert loaded is not None, "Previous file should still exist after failed write"
        assert loaded.model_dump() == original.model_dump()

    @given(data=write_failure_scenario_strategy())
    @settings(max_examples=30, deadline=10000)
    async def test_no_temp_files_remain_after_failure(
        self, data: tuple[str, ScanResult, ScanResult]
    ) -> None:
        """After a failed write, no temporary files remain in the data directory.

        **Validates: Requirements 10.5**
        """
        account_id, original, update = data
        storage, data_dir = _make_storage()

        # Save the original successfully
        await storage.save(account_id, original)

        # Attempt a second save that fails at os.replace
        with patch("os.replace", side_effect=OSError("Simulated replace failure")):
            with pytest.raises(CloudSpyglassError):
                await storage.save(account_id, update)

        # No temp files should remain (only the original .json file)
        all_files = list(data_dir.iterdir())
        temp_files = [f for f in all_files if f.suffix == ".tmp" or f.name.startswith(".")]
        assert len(temp_files) == 0, (
            f"Temp files remain after failed write: {[f.name for f in temp_files]}"
        )
