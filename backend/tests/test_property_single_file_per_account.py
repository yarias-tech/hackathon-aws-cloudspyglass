"""Property-based tests for single file per account invariant.

**Validates: Requirements 10.3**

Property 22: Single file per account invariant
- For any sequence of scan saves for the same Account_ID, exactly one file
  SHALL exist at data/{account_id}.json at any point in time.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.resources import Relationship, Resource
from backend.models.scan import RegionFailure, ScanResult
from backend.services.scan_storage import ScanStorage


# ---------------------------------------------------------------------------
# Strategies (reused from persistence round-trip tests)
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


# Strategy: a list of ScanResult objects all sharing the same account_id
@st.composite
def scan_result_sequence_strategy(draw: st.DrawFn) -> tuple[str, list[ScanResult]]:
    """Generate a sequence of ScanResults for the same account_id (1 to 5 saves)."""
    acct = draw(account_id_strategy)
    count = draw(st.integers(min_value=1, max_value=5))
    results = [draw(scan_result_strategy(account_id=acct)) for _ in range(count)]
    return acct, results


# Strategy: multiple distinct account_ids with one ScanResult each
@st.composite
def multi_account_strategy(draw: st.DrawFn) -> list[tuple[str, ScanResult]]:
    """Generate 2-4 distinct accounts each with one ScanResult."""
    accounts = draw(st.lists(
        account_id_strategy,
        min_size=2,
        max_size=4,
        unique=True,
    ))
    pairs = []
    for acct in accounts:
        result = draw(scan_result_strategy(account_id=acct))
        pairs.append((acct, result))
    return pairs


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
# Property 22: Single file per account invariant
# ---------------------------------------------------------------------------

class TestSingleFilePerAccount:
    """Sequential saves for the same account_id result in exactly one file."""

    @given(data=scan_result_sequence_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_sequential_saves_produce_exactly_one_file(
        self, data: tuple[str, list[ScanResult]]
    ) -> None:
        """For any sequence of N saves (N >= 1) with the same account_id,
        after all saves complete, exactly one file exists for that account.

        **Validates: Requirements 10.3**
        """
        account_id, scan_results = data
        storage, data_dir = _make_storage()

        # Perform N sequential saves
        for scan_result in scan_results:
            await storage.save(account_id, scan_result)

        # Exactly one file should exist in the data directory
        all_files = list(data_dir.iterdir())
        assert len(all_files) == 1, (
            f"Expected exactly 1 file after {len(scan_results)} saves, "
            f"found {len(all_files)}: {[f.name for f in all_files]}"
        )
        assert all_files[0].name == f"{account_id}.json"

    @given(data=scan_result_sequence_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_no_temp_files_remain_after_sequential_saves(
        self, data: tuple[str, list[ScanResult]]
    ) -> None:
        """No temporary files or additional files for the same account_id
        remain after sequential saves complete.

        **Validates: Requirements 10.3**
        """
        account_id, scan_results = data
        storage, data_dir = _make_storage()

        for scan_result in scan_results:
            await storage.save(account_id, scan_result)

        # Check no temp files (.tmp suffix or dot-prefixed files) remain
        all_files = list(data_dir.iterdir())
        temp_files = [f for f in all_files if f.suffix == ".tmp" or f.name.startswith(".")]
        assert len(temp_files) == 0, (
            f"Temp files remain after saves: {[f.name for f in temp_files]}"
        )

    @given(data=scan_result_sequence_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_last_save_wins(
        self, data: tuple[str, list[ScanResult]]
    ) -> None:
        """After N sequential saves, the single remaining file contains
        the data from the last save.

        **Validates: Requirements 10.3**
        """
        account_id, scan_results = data
        storage, data_dir = _make_storage()

        for scan_result in scan_results:
            await storage.save(account_id, scan_result)

        # Load and verify it matches the last saved result
        loaded = await storage.load(account_id)
        assert loaded is not None
        last_result = scan_results[-1]
        assert loaded.model_dump() == last_result.model_dump()

    @given(accounts=multi_account_strategy())
    @settings(max_examples=30, deadline=10000)
    async def test_different_accounts_each_have_one_file(
        self, accounts: list[tuple[str, ScanResult]]
    ) -> None:
        """For different account_ids, each has exactly one file
        (mutual non-interference).

        **Validates: Requirements 10.3**
        """
        storage, data_dir = _make_storage()

        # Save one result per account
        for account_id, scan_result in accounts:
            await storage.save(account_id, scan_result)

        # Each account should have exactly one file
        all_files = list(data_dir.iterdir())
        assert len(all_files) == len(accounts), (
            f"Expected {len(accounts)} files, found {len(all_files)}: "
            f"{[f.name for f in all_files]}"
        )

        # Verify each expected file exists
        expected_names = {f"{acct}.json" for acct, _ in accounts}
        actual_names = {f.name for f in all_files}
        assert actual_names == expected_names
