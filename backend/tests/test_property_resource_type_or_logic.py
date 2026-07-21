"""Property-based tests for resource type OR logic with edge visibility.

**Validates: Requirements 8.2**

Property 18: Resource type OR logic with edge visibility
- For any set of selected resource types, the filtered result SHALL contain all
  resources matching ANY of the selected types, plus any edge where at least one
  endpoint is a resource of a selected type.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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

region_strategy = st.sampled_from(VALID_AWS_REGIONS)
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)
category_strategy = st.sampled_from(RELATIONSHIP_CATEGORIES)

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

# Tag strategies
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

tags_strategy = st.dictionaries(
    keys=tag_key_strategy,
    values=tag_value_strategy,
    min_size=0,
    max_size=3,
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

    # Ensure at least 2 distinct resource types for meaningful type filter tests
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

    # Create at least one resource per chosen type
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

    # Optionally add more resources of any type
    extra = draw(st.integers(min_value=0, max_value=8))
    for _ in range(extra):
        r = draw(resource_strategy(account_id, idx))
        resources.append(r)
        idx += 1

    # Generate relationships between existing resources (including cross-type edges)
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
def scan_with_type_filters(draw):
    """Generate a scan result paired with a subset of its distinct resource types as filters."""
    scan_result = draw(scan_result_with_relationships())

    # Get distinct types present in the scan data
    available_types = list({r.resource_type for r in scan_result.resources})

    # Select a non-empty subset of types as our filter (1 to N types)
    num_selected = draw(st.integers(min_value=1, max_value=len(available_types)))
    selected_types = draw(
        st.lists(
            st.sampled_from(available_types),
            min_size=num_selected,
            max_size=num_selected,
            unique=True,
        )
    )

    return scan_result, selected_types


# ---------------------------------------------------------------------------
# Property Tests: Resource type OR logic (soundness and completeness)
# ---------------------------------------------------------------------------


class TestResourceTypeORLogicSoundness:
    """All filtered resources match at least one selected type (soundness)."""

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_filtered_resources_match_at_least_one_selected_type(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """Every resource in the filtered result has a resource_type in the selected set.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        type_set = set(type_filters)
        for node in result.diagram.nodes:
            assert node.resource_type in type_set, (
                f"Resource {node.id} has type '{node.resource_type}' which is not "
                f"in the selected types: {type_set}"
            )


class TestResourceTypeORLogicCompleteness:
    """All resources matching any selected type are included (completeness)."""

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_resources_matching_any_selected_type_are_included(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """Every resource whose type is in the selected set IS present in the result.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}
        type_set = set(type_filters)

        for resource in scan_result.resources:
            if resource.resource_type in type_set:
                assert resource.arn in filtered_arns, (
                    f"Resource {resource.arn} of type '{resource.resource_type}' "
                    f"should be in filtered result (type is in selected set: {type_set})"
                )


# ---------------------------------------------------------------------------
# Property Tests: Edge visibility (at least one endpoint)
# ---------------------------------------------------------------------------


class TestEdgeVisibilityAtLeastOneEndpoint:
    """Edges where at least one endpoint is in filtered set are included."""

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_edges_have_at_least_one_endpoint_in_filtered_set(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """Every edge in the result has at least one endpoint (source OR target) in the filtered nodes.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}

        for edge in result.diagram.edges:
            has_source = edge.source in filtered_arns
            has_target = edge.target in filtered_arns
            assert has_source or has_target, (
                f"Edge ({edge.source} -> {edge.target}) has NEITHER endpoint "
                f"in the filtered resource set: {filtered_arns}"
            )

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_no_edges_where_both_endpoints_are_outside_filtered_set(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """No edge appears in result where BOTH endpoints are outside the filtered set.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}

        for edge in result.diagram.edges:
            source_outside = edge.source not in filtered_arns
            target_outside = edge.target not in filtered_arns
            assert not (source_outside and target_outside), (
                f"Edge ({edge.source} -> {edge.target}) has both endpoints "
                f"outside the filtered resource set — should not be included"
            )

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_all_valid_edges_with_at_least_one_endpoint_are_included(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """All original edges where at least one endpoint passes the type filter are present.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        filtered_arns = {node.id for node in result.diagram.nodes}
        result_edge_pairs = {(e.source, e.target) for e in result.diagram.edges}

        # Every original relationship where at least one endpoint is in filtered set
        # should appear in the result
        for rel in scan_result.relationships:
            if rel.source_arn in filtered_arns or rel.target_arn in filtered_arns:
                assert (rel.source_arn, rel.target_arn) in result_edge_pairs, (
                    f"Edge ({rel.source_arn} -> {rel.target_arn}) should be in "
                    f"result because at least one endpoint is in the filtered set"
                )


# ---------------------------------------------------------------------------
# Property Tests: Filtered count and baseline behavior
# ---------------------------------------------------------------------------


class TestFilteredCountAndBaseline:
    """filtered_count correctness and empty type_filters baseline."""

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_equals_number_of_nodes(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """filtered_count equals the number of diagram nodes.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        assert result.filtered_count == len(result.diagram.nodes), (
            f"filtered_count ({result.filtered_count}) != "
            f"len(nodes) ({len(result.diagram.nodes)})"
        )

    @given(data=scan_with_type_filters())
    @settings(max_examples=50, deadline=None)
    def test_filtered_count_less_than_or_equal_total(
        self, data: tuple[ScanResult, list[str]]
    ) -> None:
        """filtered_count is always <= total_count.

        **Validates: Requirements 8.2**
        """
        scan_result, type_filters = data
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=type_filters)

        assert result.filtered_count <= result.total_count, (
            f"filtered_count ({result.filtered_count}) > "
            f"total_count ({result.total_count})"
        )

    @given(scan_result=scan_result_with_relationships())
    @settings(max_examples=50, deadline=None)
    def test_empty_type_filters_returns_all_resources(
        self, scan_result: ScanResult
    ) -> None:
        """When type_filters is empty, all resources and edges are returned (baseline).

        **Validates: Requirements 8.2**
        """
        engine = FilterEngine()

        result = engine.apply_filters(scan_result, type_filters=[])

        # All resources should be present
        filtered_arns = {node.id for node in result.diagram.nodes}
        original_arns = {r.arn for r in scan_result.resources}

        assert filtered_arns == original_arns, (
            f"Empty type_filters should return all resources. "
            f"Missing: {original_arns - filtered_arns}, "
            f"Extra: {filtered_arns - original_arns}"
        )

        # All edges should be present
        result_edge_pairs = {(e.source, e.target) for e in result.diagram.edges}
        original_edge_pairs = {
            (r.source_arn, r.target_arn) for r in scan_result.relationships
        }

        assert result_edge_pairs == original_edge_pairs, (
            f"Empty type_filters should return all edges. "
            f"Missing: {original_edge_pairs - result_edge_pairs}, "
            f"Extra: {result_edge_pairs - original_edge_pairs}"
        )

        # Counts should match
        assert result.filtered_count == result.total_count
        assert result.total_count == len(scan_result.resources)
