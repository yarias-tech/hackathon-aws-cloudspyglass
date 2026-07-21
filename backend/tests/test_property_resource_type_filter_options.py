"""Property-based tests for resource type filter available options.

**Validates: Requirements 8.1**

Property 17: Resource type filter available options
- For any ScanResult, the set of available resource type filter options SHALL exactly
  equal the set of distinct resource_type values present in the scan data.
- Additionally, applying type filters with ALL available types returns all resources
  (complete coverage).
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
def scan_result_strategy(draw):
    """Generate a ScanResult with resources (at least 1) and optional relationships."""
    account_id = draw(account_id_strategy)
    num_resources = draw(st.integers(min_value=1, max_value=20))

    resources = []
    for i in range(num_resources):
        r = draw(resource_strategy(account_id, i))
        resources.append(r)

    # Generate relationships between existing resources
    arns = [r.arn for r in resources]
    num_relationships = draw(st.integers(min_value=0, max_value=min(8, len(arns) * 2)))

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
def scan_result_with_multiple_types(draw):
    """Generate a ScanResult guaranteed to have at least 2 distinct resource types."""
    account_id = draw(account_id_strategy)

    # Ensure at least 2 distinct types by picking them explicitly
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
    extra = draw(st.integers(min_value=0, max_value=10))
    for _ in range(extra):
        r = draw(resource_strategy(account_id, idx))
        resources.append(r)
        idx += 1

    # Generate some relationships
    arns = [r.arn for r in resources]
    num_relationships = draw(st.integers(min_value=0, max_value=min(6, len(arns) * 2)))

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


# ---------------------------------------------------------------------------
# Property Tests: Resource type filter available options
# ---------------------------------------------------------------------------


class TestResourceTypeFilterAvailableOptions:
    """Property 17: Available type options equal the set of distinct resource_type values."""

    @given(scan_result=scan_result_strategy())
    @settings(max_examples=50, deadline=None)
    def test_distinct_types_in_scan_match_available_filter_options(
        self, scan_result: ScanResult
    ) -> None:
        """The set of distinct resource_type values in scan data defines available options.

        **Validates: Requirements 8.1**

        The available resource type filter options are derived from the distinct
        resource_type values across all resources in the ScanResult.
        """
        # Compute expected available type options from the scan data
        expected_types = {r.resource_type for r in scan_result.resources}

        # The available filter options are the distinct resource types in the scan
        actual_types = {r.resource_type for r in scan_result.resources}

        assert actual_types == expected_types, (
            f"Available type options {actual_types} do not match "
            f"distinct resource types {expected_types}"
        )

        # Verify that these types can be used as valid type_filters
        engine = FilterEngine()
        result = engine.apply_filters(
            scan_result, type_filters=list(expected_types)
        )

        # When filtering by ALL available types, all resources should be included
        assert result.filtered_count == result.total_count, (
            f"Filtering by all available types should return all resources. "
            f"Got {result.filtered_count} of {result.total_count}"
        )

    @given(scan_result=scan_result_with_multiple_types())
    @settings(max_examples=50, deadline=None)
    def test_filtering_by_all_available_types_returns_all_resources(
        self, scan_result: ScanResult
    ) -> None:
        """Applying type filter with ALL distinct types returns all resources (complete coverage).

        **Validates: Requirements 8.1**
        """
        engine = FilterEngine()

        # Get all distinct types from the scan
        all_types = list({r.resource_type for r in scan_result.resources})

        # Apply filter with all types
        result = engine.apply_filters(scan_result, type_filters=all_types)

        # Should return all resources
        filtered_arns = {node.id for node in result.diagram.nodes}
        original_arns = {r.arn for r in scan_result.resources}

        assert filtered_arns == original_arns, (
            f"Filtering by all available types should include all resources. "
            f"Missing: {original_arns - filtered_arns}, "
            f"Extra: {filtered_arns - original_arns}"
        )

        assert result.filtered_count == len(scan_result.resources), (
            f"filtered_count ({result.filtered_count}) should equal total resources "
            f"({len(scan_result.resources)}) when all types are selected"
        )

    @given(scan_result=scan_result_with_multiple_types())
    @settings(max_examples=50, deadline=None)
    def test_each_available_type_selects_only_matching_resources(
        self, scan_result: ScanResult
    ) -> None:
        """Filtering by a single available type returns only resources of that type.

        **Validates: Requirements 8.1**

        Each available type option, when selected individually, should produce
        a filtered result containing only resources of that specific type.
        """
        engine = FilterEngine()

        # Get all distinct types
        available_types = {r.resource_type for r in scan_result.resources}

        for rtype in available_types:
            result = engine.apply_filters(scan_result, type_filters=[rtype])

            # Every node in the result should have the selected type
            for node in result.diagram.nodes:
                assert node.resource_type == rtype, (
                    f"When filtering by type '{rtype}', found resource with "
                    f"type '{node.resource_type}' (node {node.id})"
                )

            # The result should contain ALL resources of that type
            expected_arns = {
                r.arn for r in scan_result.resources if r.resource_type == rtype
            }
            actual_arns = {node.id for node in result.diagram.nodes}

            assert actual_arns == expected_arns, (
                f"Filtering by type '{rtype}' should include all resources of that type. "
                f"Missing: {expected_arns - actual_arns}, "
                f"Extra: {actual_arns - expected_arns}"
            )

    @given(scan_result=scan_result_strategy())
    @settings(max_examples=50, deadline=None)
    def test_type_not_in_scan_produces_empty_result(
        self, scan_result: ScanResult
    ) -> None:
        """Filtering by a type not present in scan data yields no resources.

        **Validates: Requirements 8.1**

        Only types that exist in the scan data should produce results. A type
        that is not among the available options should match nothing.
        """
        engine = FilterEngine()

        # Find a type that does NOT exist in the scan data
        existing_types = {r.resource_type for r in scan_result.resources}
        non_existing_type = "nonexistent_service_type"

        # Ensure it doesn't accidentally match
        assert non_existing_type not in existing_types

        result = engine.apply_filters(
            scan_result, type_filters=[non_existing_type]
        )

        assert result.filtered_count == 0, (
            f"Filtering by a non-existent type should produce 0 results, "
            f"got {result.filtered_count}"
        )
        assert len(result.diagram.nodes) == 0, (
            f"Filtering by a non-existent type should produce 0 nodes, "
            f"got {len(result.diagram.nodes)}"
        )
