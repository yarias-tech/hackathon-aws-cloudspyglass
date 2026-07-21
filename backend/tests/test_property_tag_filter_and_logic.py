"""Property-based tests for tag filter AND logic with edge filtering.

**Validates: Requirements 7.1, 7.3, 7.4**

Property 14: Tag filter AND logic with edge filtering
- For any set of resources with tags and any combination of up to 10 tag key-value
  filters, the filtered result SHALL contain only resources matching ALL specified tag
  criteria, and SHALL include only edges where BOTH endpoints are in the filtered
  resource set. The filtered_count SHALL equal the number of resources in the filtered
  set and SHALL be less than or equal to total_count.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.filters import TagFilter
from backend.models.resources import Relationship, Resource
from backend.models.scan import ScanResult
from backend.services.filter_engine import FilterEngine


# ---------------------------------------------------------------------------
# Strategies
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

# Tag keys and values - constrained alphabet for stability
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

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

# Generate a tag dict with 0-5 tags
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
    """Generate tag filters that use keys/values that exist in the scan data.

    This ensures we test with filters that can actually match resources,
    making the tests more meaningful.
    """
    # Collect all tag key-value pairs from resources
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

    # Pick 1-3 filters from existing tags (some may match, testing AND logic)
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
def scan_with_tag_filters(draw):
    """Generate a scan result paired with tag filters derived from its data."""
    scan_result = draw(scan_result_with_relationships())
    tag_filters = draw(tag_filters_from_scan(scan_result))
    return scan_result, tag_filters


# ---------------------------------------------------------------------------
# Property Tests: Tag filter AND logic
# ---------------------------------------------------------------------------


class TestTagFilterANDLogic:
    """Tag filter AND logic: filtered resources must match ALL tag criteria."""

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_filtered_resources_match_all_tag_criteria(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """Every resource in the filtered result has ALL specified tag key-value pairs.

        **Validates: Requirements 7.1**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        # Every node in the result must match ALL tag filters
        filtered_arns = {node.id for node in result.diagram.nodes}
        resource_map = {r.arn: r for r in scan_result.resources}

        for arn in filtered_arns:
            resource = resource_map[arn]
            for tf in tag_filters:
                assert resource.tags.get(tf.key) == tf.value, (
                    f"Resource {arn} is in filtered result but does not have "
                    f"tag {tf.key}={tf.value}. Actual tags: {resource.tags}"
                )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_completeness_all_matching_resources_are_included(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """Every resource that matches ALL tag filters IS included in the result.

        **Validates: Requirements 7.1**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}

        # Find all resources that should match
        for resource in scan_result.resources:
            matches_all = all(
                resource.tags.get(tf.key) == tf.value for tf in tag_filters
            )
            if matches_all:
                assert resource.arn in filtered_arns, (
                    f"Resource {resource.arn} matches all tag filters but "
                    f"is not in the filtered result. Tags: {resource.tags}, "
                    f"Filters: {[(tf.key, tf.value) for tf in tag_filters]}"
                )


class TestEdgeFilteringBothEndpoints:
    """Edge filtering: only edges where BOTH endpoints are in filtered set."""

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_edges_have_both_endpoints_in_filtered_set(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """Every edge in the filtered result has both source and target in the filtered nodes.

        **Validates: Requirements 7.3**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}

        for edge in result.diagram.edges:
            assert edge.source in filtered_arns, (
                f"Edge source {edge.source} is not in the filtered resource set"
            )
            assert edge.target in filtered_arns, (
                f"Edge target {edge.target} is not in the filtered resource set"
            )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_no_extra_edges_with_missing_endpoints(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """No edge exists where either endpoint is NOT in the filtered resource set.

        **Validates: Requirements 7.3**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}

        # Verify no edge has an endpoint outside the filtered set
        for edge in result.diagram.edges:
            assert edge.source in filtered_arns and edge.target in filtered_arns, (
                f"Edge ({edge.source} -> {edge.target}) has endpoint(s) "
                f"outside filtered set: {filtered_arns}"
            )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_valid_edges_between_filtered_resources_are_included(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """All original edges where BOTH endpoints pass the filter are included.

        **Validates: Requirements 7.3**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}
        result_edge_pairs = {(e.source, e.target) for e in result.diagram.edges}

        # Every original relationship where both endpoints are in filtered set
        # should appear in the result
        for rel in scan_result.relationships:
            if rel.source_arn in filtered_arns and rel.target_arn in filtered_arns:
                assert (rel.source_arn, rel.target_arn) in result_edge_pairs, (
                    f"Edge ({rel.source_arn} -> {rel.target_arn}) should be in "
                    f"result because both endpoints are in filtered set"
                )


class TestFilteredCountCorrectness:
    """Count correctness: filtered_count == len(nodes) <= total_count."""

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_equals_number_of_nodes(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """filtered_count equals the number of diagram nodes.

        **Validates: Requirements 7.4**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        assert result.filtered_count == len(result.diagram.nodes), (
            f"filtered_count ({result.filtered_count}) != "
            f"len(nodes) ({len(result.diagram.nodes)})"
        )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_less_than_or_equal_total_count(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """filtered_count is always <= total_count.

        **Validates: Requirements 7.4**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        assert result.filtered_count <= result.total_count, (
            f"filtered_count ({result.filtered_count}) > "
            f"total_count ({result.total_count})"
        )

    @given(data=scan_with_tag_filters())
    @settings(max_examples=50, deadline=None)
    def test_total_count_equals_original_resource_count(
        self, data: tuple[ScanResult, list[TagFilter]]
    ) -> None:
        """total_count equals the number of resources in the original scan.

        **Validates: Requirements 7.4**
        """
        scan_result, tag_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=tag_filters)

        assert result.total_count == len(scan_result.resources), (
            f"total_count ({result.total_count}) != "
            f"original resource count ({len(scan_result.resources)})"
        )


class TestNoFiltersReturnsAll:
    """No filters = no filtering: when tag_filters is empty, all resources returned."""

    @given(scan_result=scan_result_with_relationships())
    @settings(max_examples=50, deadline=None)
    def test_empty_tag_filters_returns_all_resources(
        self, scan_result: ScanResult
    ) -> None:
        """When tag_filters is empty list, all resources and edges are returned.

        **Validates: Requirements 7.1**
        """
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, tag_filters=[])

        # All resources should be present
        filtered_arns = {node.id for node in result.diagram.nodes}
        original_arns = {r.arn for r in scan_result.resources}

        assert filtered_arns == original_arns, (
            f"Empty filters should return all resources. "
            f"Missing: {original_arns - filtered_arns}, "
            f"Extra: {filtered_arns - original_arns}"
        )

        # All edges should be present
        result_edge_pairs = {(e.source, e.target) for e in result.diagram.edges}
        original_edge_pairs = {
            (r.source_arn, r.target_arn) for r in scan_result.relationships
        }

        assert result_edge_pairs == original_edge_pairs, (
            f"Empty filters should return all edges. "
            f"Missing: {original_edge_pairs - result_edge_pairs}, "
            f"Extra: {result_edge_pairs - original_edge_pairs}"
        )

        # Counts should match
        assert result.filtered_count == result.total_count
        assert result.total_count == len(scan_result.resources)
