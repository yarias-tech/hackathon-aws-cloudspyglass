"""Property-based tests for combined filter intersection.

**Validates: Requirements 8.5**

Property 19: Combined filter intersection
- For any set of resources with tags and types, when both tag filters and type filters
  are active simultaneously, the filtered result SHALL contain only resources that match
  at least one selected resource type AND satisfy ALL active tag criteria. Edge filtering
  uses "both endpoints" logic (same as tag-only). The combined result is a subset of both
  the tag-only result and the type-only result.
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

# Generate a tag dict with 1-5 tags (min 1 to ensure tag filters can be derived)
tags_strategy = st.dictionaries(
    keys=tag_key_strategy,
    values=tag_value_strategy,
    min_size=1,
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
    """Generate a ScanResult with multiple resource types and relationships."""
    account_id = draw(account_id_strategy)

    # Ensure at least 2 distinct resource types for meaningful combined filter tests
    num_guaranteed_types = draw(st.integers(min_value=2, max_value=len(RESOURCE_TYPES)))
    chosen_types = draw(
        st.lists(
            st.sampled_from(RESOURCE_TYPES),
            min_size=num_guaranteed_types,
            max_size=num_guaranteed_types,
            unique=True,
        )
    )

    resources = []
    idx = 0

    # Create at least one resource per chosen type (with tags)
    for rtype in chosen_types:
        region = draw(region_strategy)
        tags = draw(tags_strategy)
        resources.append(
            Resource(
                arn=f"arn:aws:{rtype}:{region}:{account_id}:resource/res-{idx:04d}",
                resource_type=rtype,
                name=f"resource-{idx}",
                region=region,
                tags=tags,
            )
        )
        idx += 1

    # Add more resources of any type
    extra = draw(st.integers(min_value=0, max_value=8))
    for _ in range(extra):
        r = draw(resource_strategy(account_id, idx))
        resources.append(r)
        idx += 1

    # Generate relationships between existing resources
    arns = [r.arn for r in resources]
    num_relationships = draw(st.integers(min_value=1, max_value=min(12, len(arns) * 2)))

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
    return ScanResult(
        account_id=account_id,
        scan_timestamp="2024-01-15T10:30:00Z",
        resources=resources,
        relationships=relationships,
        failures=[],
        scanned_regions=[region],
        total_scan_duration_ms=1000,
    )


@st.composite
def scan_with_combined_filters(draw):
    """Generate a scan result paired with both tag filters and type filters.

    Tag filters are derived from existing tags in the scan data to ensure
    meaningful intersection testing. Type filters are a subset of types present.
    """
    scan_result = draw(scan_result_with_relationships())

    # Derive tag filters from existing tag key-value pairs in the data
    existing_tags = []
    for resource in scan_result.resources:
        for key, value in resource.tags.items():
            existing_tags.append((key, value))

    # Pick 1-3 tag filters from existing tags
    num_tag_filters = draw(
        st.integers(min_value=1, max_value=min(3, len(existing_tags)))
    )
    chosen_tag_indices = draw(
        st.lists(
            st.sampled_from(range(len(existing_tags))),
            min_size=num_tag_filters,
            max_size=num_tag_filters,
            unique=True,
        )
    )
    tag_filters = [
        TagFilter(key=existing_tags[i][0], value=existing_tags[i][1])
        for i in chosen_tag_indices
    ]

    # Derive type filters from distinct resource types present
    available_types = list({r.resource_type for r in scan_result.resources})
    num_type_filters = draw(
        st.integers(min_value=1, max_value=len(available_types))
    )
    type_filters = draw(
        st.lists(
            st.sampled_from(available_types),
            min_size=num_type_filters,
            max_size=num_type_filters,
            unique=True,
        )
    )

    return scan_result, tag_filters, type_filters


# ---------------------------------------------------------------------------
# Property Tests: Combined filter soundness
# ---------------------------------------------------------------------------


class TestCombinedFilterSoundness:
    """Every resource in the result matches ALL tags AND at least one type."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_filtered_resources_match_all_tags_and_at_least_one_type(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """Every resource in the combined-filtered result has ALL tag criteria
        AND a resource_type in the selected type set.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        type_set = set(type_filters)
        resource_map = {r.arn: r for r in scan_result.resources}
        filtered_arns = {node.id for node in result.diagram.nodes}

        for arn in filtered_arns:
            resource = resource_map[arn]
            # Must match ALL tag filters
            for tf in tag_filters:
                assert resource.tags.get(tf.key) == tf.value, (
                    f"Resource {arn} is in combined-filtered result but does not "
                    f"have tag {tf.key}={tf.value}. Actual tags: {resource.tags}"
                )
            # Must match at least one type
            assert resource.resource_type in type_set, (
                f"Resource {arn} has type '{resource.resource_type}' which is not "
                f"in the selected types: {type_set}"
            )


# ---------------------------------------------------------------------------
# Property Tests: Combined filter completeness
# ---------------------------------------------------------------------------


class TestCombinedFilterCompleteness:
    """Every resource matching ALL tags AND at least one type IS included."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_resources_matching_combined_criteria_are_included(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """Every resource that matches ALL tags AND at least one selected type
        IS present in the filtered result.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        filtered_arns = {node.id for node in result.diagram.nodes}
        type_set = set(type_filters)

        for resource in scan_result.resources:
            matches_all_tags = all(
                resource.tags.get(tf.key) == tf.value for tf in tag_filters
            )
            matches_type = resource.resource_type in type_set

            if matches_all_tags and matches_type:
                assert resource.arn in filtered_arns, (
                    f"Resource {resource.arn} matches all tag filters and has "
                    f"type '{resource.resource_type}' in {type_set}, but is not "
                    f"in the filtered result. Tags: {resource.tags}"
                )


# ---------------------------------------------------------------------------
# Property Tests: Edge filtering (both endpoints)
# ---------------------------------------------------------------------------


class TestCombinedEdgeFilteringBothEndpoints:
    """When combined filters are active, edges require BOTH endpoints in filtered set."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_edges_have_both_endpoints_in_combined_filtered_set(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """Every edge in the combined-filtered result has both source and target
        in the filtered nodes.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        filtered_arns = {node.id for node in result.diagram.nodes}

        for edge in result.diagram.edges:
            assert edge.source in filtered_arns, (
                f"Edge source {edge.source} is not in the combined-filtered set"
            )
            assert edge.target in filtered_arns, (
                f"Edge target {edge.target} is not in the combined-filtered set"
            )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_valid_edges_between_combined_filtered_resources_are_included(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """All original edges where BOTH endpoints pass the combined filter are included.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        filtered_arns = {node.id for node in result.diagram.nodes}
        result_edge_pairs = {(e.source, e.target) for e in result.diagram.edges}

        for rel in scan_result.relationships:
            if rel.source_arn in filtered_arns and rel.target_arn in filtered_arns:
                assert (rel.source_arn, rel.target_arn) in result_edge_pairs, (
                    f"Edge ({rel.source_arn} -> {rel.target_arn}) should be in "
                    f"result because both endpoints are in the combined-filtered set"
                )


# ---------------------------------------------------------------------------
# Property Tests: Count correctness
# ---------------------------------------------------------------------------


class TestCombinedFilterCountCorrectness:
    """filtered_count == len(nodes) <= total_count."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_equals_number_of_nodes(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """filtered_count equals the number of diagram nodes.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        assert result.filtered_count == len(result.diagram.nodes), (
            f"filtered_count ({result.filtered_count}) != "
            f"len(nodes) ({len(result.diagram.nodes)})"
        )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_less_than_or_equal_total_count(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """filtered_count is always <= total_count.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )

        assert result.filtered_count <= result.total_count, (
            f"filtered_count ({result.filtered_count}) > "
            f"total_count ({result.total_count})"
        )


# ---------------------------------------------------------------------------
# Property Tests: Combined is stricter than individual
# ---------------------------------------------------------------------------


class TestCombinedStricterThanIndividual:
    """Combined result is a subset of both tag-only result and type-only result."""

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_combined_result_is_subset_of_tag_only_result(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """The combined-filtered resource set is a subset of the tag-only filtered set.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        # Combined result
        combined_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )
        combined_arns = {node.id for node in combined_result.diagram.nodes}

        # Tag-only result
        tag_only_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=[]
        )
        tag_only_arns = {node.id for node in tag_only_result.diagram.nodes}

        assert combined_arns.issubset(tag_only_arns), (
            f"Combined result is NOT a subset of tag-only result. "
            f"Extra in combined: {combined_arns - tag_only_arns}"
        )

    @given(data=scan_with_combined_filters())
    @settings(max_examples=50, deadline=None)
    def test_combined_result_is_subset_of_type_only_result(
        self, data: tuple[ScanResult, list[TagFilter], list[str]]
    ) -> None:
        """The combined-filtered resource set is a subset of the type-only filtered set.

        **Validates: Requirements 8.5**
        """
        scan_result, tag_filters, type_filters = data
        engine = FilterEngine()

        # Combined result
        combined_result = engine.apply_filters(
            scan_result, tag_filters=tag_filters, type_filters=type_filters
        )
        combined_arns = {node.id for node in combined_result.diagram.nodes}

        # Type-only result
        type_only_result = engine.apply_filters(
            scan_result, tag_filters=[], type_filters=type_filters
        )
        type_only_arns = {node.id for node in type_only_result.diagram.nodes}

        assert combined_arns.issubset(type_only_arns), (
            f"Combined result is NOT a subset of type-only result. "
            f"Extra in combined: {combined_arns - type_only_arns}"
        )
