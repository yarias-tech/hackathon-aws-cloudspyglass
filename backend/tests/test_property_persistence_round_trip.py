"""Property-based tests for scan result persistence round-trip.

**Validates: Requirements 10.1**

Property 21: Scan result persistence round-trip
- For any valid ScanResult object, serializing it to data/{account_id}.json
  and then deserializing the file SHALL produce an object equivalent to the original.
"""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.resources import Relationship, Resource
from backend.models.scan import RegionFailure, ScanResult
from backend.services.scan_storage import ScanStorage


# ---------------------------------------------------------------------------
# Strategies
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

# Tag key/value strategies (safe printable text)
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

# Simple attribute values (JSON-serializable primitives)
attribute_value_strategy = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.none(),
)


# Strategy: a single Resource
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
        max_size=5,
    ))

    attributes = draw(st.dictionaries(
        keys=tag_key_strategy,
        values=attribute_value_strategy,
        min_size=0,
        max_size=3,
    ))

    creation_date = draw(st.one_of(st.none(), iso_timestamp_strategy))
    iam_role = draw(st.one_of(
        st.none(),
        st.just(f"arn:aws:iam::{acct}:role/{name}-role"),
    ))

    return Resource(
        arn=arn,
        resource_type=rtype,
        name=name,
        region=region,
        tags=tags,
        creation_date=creation_date,
        iam_role=iam_role,
        attributes=attributes,
        is_external=draw(st.booleans()),
        is_unresolved=draw(st.booleans()),
    )


# Strategy: a Relationship (referencing ARN-like strings)
@st.composite
def relationship_strategy(draw: st.DrawFn) -> Relationship:
    """Generate a valid Relationship."""
    acct = draw(account_id_strategy)
    region = draw(region_strategy)
    source_type = draw(resource_type_strategy)
    target_type = draw(resource_type_strategy)

    source_arn = f"arn:aws:{source_type}:{region}:{acct}:src-{draw(st.integers(1, 9999))}"
    target_arn = f"arn:aws:{target_type}:{region}:{acct}:tgt-{draw(st.integers(1, 9999))}"

    return Relationship(
        source_arn=source_arn,
        target_arn=target_arn,
        category=draw(category_strategy),
        derived_from=draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._"),
            min_size=1,
            max_size=30,
        )),
    )


# Strategy: a RegionFailure
@st.composite
def region_failure_strategy(draw: st.DrawFn) -> RegionFailure:
    """Generate a valid RegionFailure."""
    return RegionFailure(
        region=draw(region_strategy),
        resource_type=draw(resource_type_strategy),
        error_message=draw(st.text(min_size=1, max_size=100)),
        timestamp=draw(iso_timestamp_strategy),
    )


# Strategy: a complete ScanResult
@st.composite
def scan_result_strategy(draw: st.DrawFn) -> ScanResult:
    """Generate a valid ScanResult with varied content."""
    acct = draw(account_id_strategy)
    resources = draw(st.lists(resource_strategy(), min_size=0, max_size=10))
    relationships = draw(st.lists(relationship_strategy(), min_size=0, max_size=5))
    failures = draw(st.lists(region_failure_strategy(), min_size=0, max_size=3))
    scanned_regions = draw(st.lists(region_strategy, min_size=1, max_size=5))

    return ScanResult(
        account_id=acct,
        scan_timestamp=draw(iso_timestamp_strategy),
        resources=resources,
        relationships=relationships,
        failures=failures,
        scanned_regions=scanned_regions,
        total_scan_duration_ms=draw(st.integers(min_value=0, max_value=600_000)),
    )


# ---------------------------------------------------------------------------
# Helper: create a fresh ScanStorage with a temporary directory
# ---------------------------------------------------------------------------

def _make_storage() -> tuple[ScanStorage, Path]:
    """Create a ScanStorage with a fresh temporary directory."""
    tmp_dir = Path(tempfile.mkdtemp())
    data_dir = tmp_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return ScanStorage(data_dir=data_dir), data_dir


# ---------------------------------------------------------------------------
# Property 21: Persistence round-trip equivalence
# ---------------------------------------------------------------------------

class TestPersistenceRoundTrip:
    """Serialize → deserialize produces equivalent ScanResult."""

    @given(scan_result=scan_result_strategy())
    @settings(max_examples=50, deadline=10000)
    async def test_round_trip_produces_equivalent_result(
        self, scan_result: ScanResult
    ) -> None:
        """For any valid ScanResult, save then load yields an equivalent object.

        This verifies that the JSON serialization (model_dump_json) and
        deserialization (model_validate from JSON) are lossless for all
        fields: account_id, scan_timestamp, resources, relationships,
        failures, scanned_regions, and total_scan_duration_ms.
        """
        storage, _ = _make_storage()
        account_id = scan_result.account_id

        # Serialize (save)
        await storage.save(account_id, scan_result)

        # Deserialize (load)
        loaded = await storage.load(account_id)

        # Must successfully load
        assert loaded is not None, "Loaded result should not be None after save"

        # Top-level fields
        assert loaded.account_id == scan_result.account_id
        assert loaded.scan_timestamp == scan_result.scan_timestamp
        assert loaded.scanned_regions == scan_result.scanned_regions
        assert loaded.total_scan_duration_ms == scan_result.total_scan_duration_ms

        # Resources equivalence
        assert len(loaded.resources) == len(scan_result.resources)
        for orig, restored in zip(scan_result.resources, loaded.resources):
            assert restored.arn == orig.arn
            assert restored.resource_type == orig.resource_type
            assert restored.name == orig.name
            assert restored.region == orig.region
            assert restored.tags == orig.tags
            assert restored.creation_date == orig.creation_date
            assert restored.iam_role == orig.iam_role
            assert restored.attributes == orig.attributes
            assert restored.is_external == orig.is_external
            assert restored.is_unresolved == orig.is_unresolved

        # Relationships equivalence
        assert len(loaded.relationships) == len(scan_result.relationships)
        for orig, restored in zip(scan_result.relationships, loaded.relationships):
            assert restored.source_arn == orig.source_arn
            assert restored.target_arn == orig.target_arn
            assert restored.category == orig.category
            assert restored.derived_from == orig.derived_from

        # Failures equivalence
        assert len(loaded.failures) == len(scan_result.failures)
        for orig, restored in zip(scan_result.failures, loaded.failures):
            assert restored.region == orig.region
            assert restored.resource_type == orig.resource_type
            assert restored.error_message == orig.error_message
            assert restored.timestamp == orig.timestamp

    @given(scan_result=scan_result_strategy())
    @settings(max_examples=30, deadline=10000)
    async def test_round_trip_model_equality(
        self, scan_result: ScanResult
    ) -> None:
        """The Pydantic model_dump of saved and loaded results are identical.

        This provides a stronger equivalence check using Pydantic's built-in
        serialization, ensuring no data transformation occurs during persistence.
        """
        storage, _ = _make_storage()
        account_id = scan_result.account_id

        await storage.save(account_id, scan_result)
        loaded = await storage.load(account_id)

        assert loaded is not None
        assert loaded.model_dump() == scan_result.model_dump()

    @given(scan_result=scan_result_strategy())
    @settings(max_examples=20, deadline=10000)
    async def test_saved_file_is_valid_utf8_json(
        self, scan_result: ScanResult
    ) -> None:
        """The persisted file is always valid UTF-8 encoded JSON.

        This ensures Requirement 10.1's encoding specification is met
        regardless of the content of the ScanResult.
        """
        storage, data_dir = _make_storage()
        account_id = scan_result.account_id

        await storage.save(account_id, scan_result)

        file_path = data_dir / f"{account_id}.json"
        assert file_path.exists(), "File should exist after save"

        # Read as raw bytes and verify UTF-8 decoding
        raw_bytes = file_path.read_bytes()
        text = raw_bytes.decode("utf-8")  # Should not raise

        # Verify it's valid JSON
        parsed = json.loads(text)
        assert isinstance(parsed, dict)
        assert parsed["account_id"] == account_id
