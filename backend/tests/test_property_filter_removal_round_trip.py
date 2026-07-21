"""Property-based tests for filter removal round-trip.

**Validates: Requirements 7.6**

Property 16: Filter removal round-trip
- For any diagram data, applying tag/type filters and then removing all filters
  SHALL produce a result equivalent to the original unfiltered diagram.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.filters import TagFilter
from backend.models.resources import Relationship, Resource
from backend.models.scan import ScanResult
from backend.services.filter_engine import FilterEngine


# ---------------------------------------------------------------------------
# Strategies (reused patterns from existing property tests)
# ---------------------------------------------------------------------------

VALID_AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-central-1",
    "ap-southeast-1",
    "ap-northeast-1",
]

RESOURCE_TYPES = ["ec2", "lambda", "s3", "rds", "alb", "nlb", "sqs", "sns"]
RELATIONSHIP_CATEGORIES = ["network", "iam", "event", "data"]

tag_key_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_",
    min_size=1,
    max_size=20,
)

tag_value_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.",
    min_size=1,
    max_size=30,
)

region_strategy = st.sampled_from(VALID_AWS_REGIONS)
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)
category_strategy = st.sampled_from(RELATIONSHIP_CATEGORIES)
account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

tags_strategy = st.dictionaries(
    keys=tag_key_strategy,
    values=tag_value_strategy,
    min_size=0,
    max_size=5,
)


def resource_strategy(account_id: str, idx: int):
    """Build a resource strategy with a unique ARN based on index."""
    return st.builds(
        lambda region, rtype, tags: Resource(
            arn=f"arn:aws:{rtype}:{region}:{account_id}:resource/res-{idx:04d}",
            resource_type=rtype,
            name=f"resource-{idx}",
            region=region,
            tags=tags,
        ),
        region=region_strategy,
        rtype=resource_type_strategy,
        tags=tags_strategy,
    )


@st.composite
def scan_result_with_relationships(draw):
    """Generate a ScanResult with resources and relationships between them."""
    account_id = draw(account_id_strategy)
    num_resources = draw(st.integers(min_value=2, max_value=15))

    resources = []
    for i in range(num_resources):
        r = draw(resource_strategy(account_id, i))
        resources.append(r)

    # Generate relationships between existing resources
    arns = [r.arn for r in resources]
    num_relationships = draw(st.integers(min_value=0, max_value=min(10, len(arns) * 2)))

    relationships = []
    for _ in range(num_relationships):
        source_arn = draw(st.sampled_from(arns))
        target_arn = draw(st.sampled_from(arns))
        if source_arn != target_arn:
            category = draw(category_strategy)
            relationships.append(
                Relationship(
                    source_arn=source_arn,
                    target_arn=target_arn,
                    category=category,
                    derived_from="TestAttribute",
                )
            )

    region = draw(region_strategy)
    scan_result = ScanResult(
        account_id=account_id,
        scan_timestamp="2024-01-15T10:30:00Z",
        resources=resources,
        relationships=relationships,
        failures=[],
        scanned_regions=[region],
        total_scan_duration_ms=1000,
    )

    return scan_result


@st.composite
def tag_filters_from_scan(draw, scan_result: ScanResult):
    """Generate tag filters using keys/values present in the scan data."""
    existing_tags = []
    for resource in scan_result.resources:
        for key, value in resource.tags.items():
            existing_tags.append((key, value))

    if not existing_tags:
        # No tags in data - generate random filters (will match nothing)
        num_filters = draw(st.integers(min_value=1, max_value=3))
        filters = []
        for _ in range(num_filters):
            key = draw(tag_key_strategy)
            value = draw(tag_value_strategy)
            filters.append(TagFilter(key=key, value=value))
        return filters

    num_filters = draw(st.integers(min_value=1, max_value=min(3, len(existing_tags))))
    chosen_indices = draw(
        st.lists(
            st.sampled_from(range(len(existing_tags))),
            min_size=num_filters,
            max_size=num_filters,
            unique=True,
        )
    )

    filters = [
        TagFilter(key=existing_tags[i][0], value=existing_tags[i][1])
        for i in chosen_indices
    ]
    return filters


@st.composite
def type_filters_from_scan(draw, scan_result: ScanResult):
    """Generate type filters using resource types present in the scan data."""
    existing_types = list({r.resource_type for r in scan_result.resources})

    if not existing_types:
        return [draw(resource_type_strategy)]

    num_filters = draw(st.integers(min_value=1, max_value=min(3, len(existing_types))))
    chosen = draw(
        st.lists(
            st.sampled_from(existing_types),
            min_size=num_filters,
            max_size=num_filters,
            unique=True,
        )
    )
    return chosen


@st.composite
def scan_with_tag_filters(draw):
    """Generate a scan result paired with tag filters derived from its data."""
    scan_result = draw(scan_result_with_relationships())
    tag_filters = draw(tag_filters_from_scan(scan_result))
    return scan_result, tag_filters


@st.composite
def scan_with_type_filters(draw):
    """Generate a scan result paired with type filters derived from its data."""
    scan_result = draw(scan_result_with_relationships())
    type_filters = draw(type_filters_from_scan(scan_result))
    return scan_result, type_filters


@st.composite
def scan_with_combined_filters(draw):
    """Generate a scan result paired with both tag and type filters."""
    scan_result = draw(scan_result_with_relationships())
    tag_filters = draw(tag_filters_from_scan(scan_result))
    type_filters = draw(type_filters_from_scan(scan_result))
    return scan_result, tag_filters, type_filters


# ---------------------------------------------------------------------------
# Helper: get unfiltered baseline
# ---------------------------------------------------------------------------


def get_unfiltered_result(engine: FilterEngine, scan_result: ScanResult):
    """Get the unfiltered (no filters applied) result as the baseline."""
    return engine.apply_filters(scan_result, tag_filters=None, type_filters=None)


# ---------------------------------------------------------------------------
# Property Tests: Filter removal round-trip
# ---------------------------------------------------------------------------


class TestFilterRemovalRoundTripTagFilters:
    """Applying tag filters then removing them produces the original unfiltered result."""

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_tag_filters_restores_all_resources(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """After applying and removing tag filters, all resources are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        # Step 1: Apply filters (may reduce the set)
        _filtered_result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        # Step 2: Remove all filters (apply with no filters)
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        # Step 3: Get the baseline unfiltered result
        baseline_result = get_unfiltered_result(engine, scan_result)

        # The restored result should have the same nodes as the baseline
        restored_arns = {node.id for node in restored_result.diagram.nodes}
        baseline_arns = {node.id for node in baseline_result.diagram.nodes}

        assert restored_arns == baseline_arns, (
            f"After removing tag filters, resource set differs from baseline. "
            f"Missing: {baseline_arns - restored_arns}, "
            f"Extra: {restored_arns - baseline_arns}"
        )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_tag_filters_restores_all_edges(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """After applying and removing tag filters, all edges are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        # Step 1: Apply filters
        _filtered_result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        # Step 2: Remove all filters
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        # Step 3: Baseline
        baseline_result = get_unfiltered_result(engine, scan_result)

        restored_edges = {
            (e.source, e.target) for e in restored_result.diagram.edges
        }
        baseline_edges = {
            (e.source, e.target) for e in baseline_result.diagram.edges
        }

        assert restored_edges == baseline_edges, (
            f"After removing tag filters, edge set differs from baseline. "
            f"Missing: {baseline_edges - restored_edges}, "
            f"Extra: {restored_edges - baseline_edges}"
        )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_tag_filters_restores_counts(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """After removing tag filters, filtered_count == total_count.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        # Apply then remove
        _filtered_result = engine.apply_filters(scan_result, tag_filters=tag_filters)
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        assert restored_result.filtered_count == restored_result.total_count, (
            f"After removing all filters, filtered_count ({restored_result.filtered_count}) "
            f"should equal total_count ({restored_result.total_count})"
        )
        assert restored_result.total_count == len(scan_result.resources), (
            f"total_count ({restored_result.total_count}) should equal "
            f"original resource count ({len(scan_result.resources)})"
        )


class TestFilterRemovalRoundTripTypeFilters:
    """Applying type filters then removing them produces the original unfiltered result."""

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_type_filters_restores_all_resources(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """After applying and removing type filters, all resources are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        # Apply type filters
        _filtered_result = engine.apply_filters(scan_result, type_filters=type_filters)

        # Remove all filters
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        baseline_result = get_unfiltered_result(engine, scan_result)

        restored_arns = {node.id for node in restored_result.diagram.nodes}
        baseline_arns = {node.id for node in baseline_result.diagram.nodes}

        assert restored_arns == baseline_arns, (
            f"After removing type filters, resource set differs from baseline. "
            f"Missing: {baseline_arns - restored_arns}, "
            f"Extra: {restored_arns - baseline_arns}"
        )

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_type_filters_restores_all_edges(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """After applying and removing type filters, all edges are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        _filtered_result = engine.apply_filters(scan_result, type_filters=type_filters)
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        baseline_result = get_unfiltered_result(engine, scan_result)

        restored_edges = {
            (e.source, e.target) for e in restored_result.diagram.edges
        }
        baseline_edges = {
            (e.source, e.target) for e in baseline_result.diagram.edges
        }

        assert restored_edges == baseline_edges, (
            f"After removing type filters, edge set differs from baseline. "
            f"Missing: {baseline_edges - restored_edges}, "
            f"Extra: {restored_edges - baseline_edges}"
        )

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_type_filters_restores_counts(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """After removing type filters, filtered_count == total_count.

        **Validates: Requirements 7.6**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        _filtered_result = engine.apply_filters(scan_result, type_filters=type_filters)
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        assert restored_result.filtered_count == restored_result.total_count
        assert restored_result.total_count == len(scan_result.resources)


class TestFilterRemovalRoundTripCombinedFilters:
    """Applying combined tag+type filters then removing them restores the original."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_combined_filters_restores_all_resources(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """After applying and removing combined filters, all resources are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        # Apply combined filters
        _filtered_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        # Remove all filters
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        baseline_result = get_unfiltered_result(engine, scan_result)

        restored_arns = {node.id for node in restored_result.diagram.nodes}
        baseline_arns = {node.id for node in baseline_result.diagram.nodes}

        assert restored_arns == baseline_arns, (
            f"After removing combined filters, resource set differs from baseline. "
            f"Missing: {baseline_arns - restored_arns}, "
            f"Extra: {restored_arns - baseline_arns}"
        )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_combined_filters_restores_all_edges(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """After applying and removing combined filters, all edges are restored.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        _filtered_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        baseline_result = get_unfiltered_result(engine, scan_result)

        restored_edges = {
            (e.source, e.target) for e in restored_result.diagram.edges
        }
        baseline_edges = {
            (e.source, e.target) for e in baseline_result.diagram.edges
        }

        assert restored_edges == baseline_edges, (
            f"After removing combined filters, edge set differs from baseline. "
            f"Missing: {baseline_edges - restored_edges}, "
            f"Extra: {restored_edges - baseline_edges}"
        )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_removing_combined_filters_restores_counts(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """After removing combined filters, filtered_count == total_count.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        _filtered_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        assert restored_result.filtered_count == restored_result.total_count
        assert restored_result.total_count == len(scan_result.resources)


class TestFilterRemovalIdempotence:
    """Removing filters multiple times produces same result (idempotent)."""

    @given(scan_result=scan_result_with_relationships())
    @settings(max_examples=50, deadline=None)
    def test_unfiltered_result_is_idempotent(self, scan_result: ScanResult) -> None:
        """Calling apply_filters with no filters multiple times gives same result.

        **Validates: Requirements 7.6**
        """
        engine = FilterEngine()

        result_1 = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )
        result_2 = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        arns_1 = {node.id for node in result_1.diagram.nodes}
        arns_2 = {node.id for node in result_2.diagram.nodes}

        assert arns_1 == arns_2, "Unfiltered results should be identical across calls"

        edges_1 = {(e.source, e.target) for e in result_1.diagram.edges}
        edges_2 = {(e.source, e.target) for e in result_2.diagram.edges}

        assert edges_1 == edges_2, "Unfiltered edge sets should be identical across calls"

        assert result_1.filtered_count == result_2.filtered_count
        assert result_1.total_count == result_2.total_count

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_apply_remove_apply_remove_produces_same_baseline(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """Applying and removing filters repeatedly always returns to the same baseline.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        # First round: apply then remove
        engine.apply_filters(scan_result, tag_filters=tag_filters)
        restored_1 = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        # Second round: apply then remove again
        engine.apply_filters(scan_result, tag_filters=tag_filters)
        restored_2 = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        arns_1 = {node.id for node in restored_1.diagram.nodes}
        arns_2 = {node.id for node in restored_2.diagram.nodes}

        assert arns_1 == arns_2, (
            "Repeated apply/remove cycles should produce identical results"
        )

        edges_1 = {(e.source, e.target) for e in restored_1.diagram.edges}
        edges_2 = {(e.source, e.target) for e in restored_2.diagram.edges}

        assert edges_1 == edges_2


class TestFilterRemovalMatchesOriginalScanData:
    """Removing filters produces result matching the original scan data exactly."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_restored_nodes_match_original_resources(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """After removing all filters, every original resource appears as a node.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        # Apply combined filters
        engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        # Remove all filters
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        restored_arns = {node.id for node in restored_result.diagram.nodes}
        original_arns = {r.arn for r in scan_result.resources}

        assert restored_arns == original_arns, (
            f"Restored diagram should contain exactly the original resources. "
            f"Missing: {original_arns - restored_arns}, "
            f"Extra: {restored_arns - original_arns}"
        )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_restored_edges_match_original_relationships(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """After removing all filters, every original relationship appears as an edge.

        **Validates: Requirements 7.6**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        # Apply combined filters
        engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        # Remove all filters
        restored_result = engine.apply_filters(
            scan_result, tag_filters=None, type_filters=None
        )

        restored_edges = {
            (e.source, e.target) for e in restored_result.diagram.edges
        }
        original_edges = {
            (r.source_arn, r.target_arn) for r in scan_result.relationships
        }

        assert restored_edges == original_edges, (
            f"Restored diagram should contain exactly the original relationships. "
            f"Missing: {original_edges - restored_edges}, "
            f"Extra: {restored_edges - original_edges}"
        )
