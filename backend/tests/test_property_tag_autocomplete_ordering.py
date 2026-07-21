"""Property-based tests for tag autocomplete frequency ordering.

**Validates: Requirements 7.2**

Property 15: Tag autocomplete frequency ordering
- For any scan result containing tagged resources, the tag suggestion list SHALL
  return at most 20 entries ordered by descending frequency of occurrence in the
  current scan data.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.resources import Resource
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

# Constrained tag key/value alphabets for stable generation
tag_key_strategy = st.sampled_from(
    ["Environment", "Team", "Project", "Owner", "CostCenter", "Service",
     "Application", "Version", "Tier", "Department", "Region", "Stack"]
)

tag_value_strategy = st.sampled_from(
    ["production", "staging", "development", "testing", "platform", "backend",
     "frontend", "data", "infra", "alpha", "beta", "v1", "v2", "core", "edge"]
)

region_strategy = st.sampled_from(VALID_AWS_REGIONS)
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)

# Account ID strategy (12-digit numeric)
account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

# Generate a tag dict with 1-5 tags (ensure resources have tags for meaningful tests)
tags_strategy = st.dictionaries(
    keys=tag_key_strategy,
    values=tag_value_strategy,
    min_size=1,
    max_size=5,
)


@st.composite
def scan_result_with_tags(draw):
    """Generate a ScanResult with resources that have tags.

    Produces 5-30 resources to create meaningful frequency distributions.
    """
    account_id = draw(account_id_strategy)
    num_resources = draw(st.integers(min_value=5, max_value=30))

    resources = []
    for i in range(num_resources):
        region = draw(region_strategy)
        rtype = draw(resource_type_strategy)
        tags = draw(tags_strategy)
        resources.append(
            Resource(
                arn=f"arn:aws:{rtype}:{region}:{account_id}:resource/res-{i:04d}",
                resource_type=rtype,
                name=f"resource-{i}",
                region=region,
                tags=tags,
            )
        )

    return ScanResult(
        account_id=account_id,
        scan_timestamp="2024-01-15T10:30:00Z",
        resources=resources,
        relationships=[],
        failures=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1000,
    )


@st.composite
def scan_result_with_many_distinct_tags(draw):
    """Generate a ScanResult with enough distinct tag pairs to exceed 20.

    This ensures we properly test the ≤20 limit.
    """
    account_id = draw(account_id_strategy)

    # Use a wider set of keys and values to generate >20 distinct pairs
    extended_keys = [f"Key{i}" for i in range(25)]
    extended_values = [f"val{i}" for i in range(25)]

    num_resources = draw(st.integers(min_value=25, max_value=40))

    resources = []
    for i in range(num_resources):
        region = draw(region_strategy)
        rtype = draw(resource_type_strategy)
        # Give each resource a unique tag from the extended set
        key = draw(st.sampled_from(extended_keys))
        value = draw(st.sampled_from(extended_values))
        # Also add some shared tags to create frequency variation
        tags = {key: value}
        if draw(st.booleans()):
            tags["SharedKey"] = "shared-value"
        resources.append(
            Resource(
                arn=f"arn:aws:{rtype}:{region}:{account_id}:resource/res-{i:04d}",
                resource_type=rtype,
                name=f"resource-{i}",
                region=region,
                tags=tags,
            )
        )

    return ScanResult(
        account_id=account_id,
        scan_timestamp="2024-01-15T10:30:00Z",
        resources=resources,
        relationships=[],
        failures=[],
        scanned_regions=["us-east-1"],
        total_scan_duration_ms=1000,
    )


# Prefix strategy - empty string or a short prefix from known keys/values
prefix_strategy = st.one_of(
    st.just(""),
    st.sampled_from(["Env", "Team", "pro", "stag", "dev", "v", "P", "O", "S"]),
)


# ---------------------------------------------------------------------------
# Property Tests: Tag autocomplete frequency ordering
# ---------------------------------------------------------------------------


class TestTagSuggestionsMaxEntries:
    """Suggestions never exceed 20 entries."""

    @given(scan_result=scan_result_with_tags(), prefix=prefix_strategy)
    @settings(max_examples=50, deadline=None)
    def test_suggestions_return_at_most_20_entries(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """The tag suggestion list SHALL return at most 20 entries.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        assert len(suggestions) <= 20, (
            f"Expected at most 20 suggestions, got {len(suggestions)}"
        )

    @given(scan_result=scan_result_with_many_distinct_tags(), prefix=st.just(""))
    @settings(max_examples=30, deadline=None)
    def test_suggestions_capped_at_20_when_more_tags_exist(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """When more than 20 distinct tag pairs exist, result is capped at 20.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        # Count distinct tag pairs
        distinct_pairs = set()
        for resource in scan_result.resources:
            for key, value in resource.tags.items():
                distinct_pairs.add((key, value))

        if len(distinct_pairs) > 20:
            assert len(suggestions) == 20, (
                f"Expected exactly 20 suggestions when {len(distinct_pairs)} "
                f"distinct tag pairs exist, got {len(suggestions)}"
            )
        else:
            assert len(suggestions) <= 20


class TestTagSuggestionsDescendingFrequency:
    """Suggestions are ordered by descending frequency."""

    @given(scan_result=scan_result_with_tags(), prefix=prefix_strategy)
    @settings(max_examples=50, deadline=None)
    def test_suggestions_ordered_by_descending_count(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """Each suggestion's count is >= the next suggestion's count.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        if len(suggestions) < 2:
            return  # Nothing to check with 0-1 results

        for i in range(len(suggestions) - 1):
            assert suggestions[i].count >= suggestions[i + 1].count, (
                f"Suggestions not in descending frequency order at index {i}: "
                f"({suggestions[i].key}={suggestions[i].value}, count={suggestions[i].count}) "
                f"is followed by "
                f"({suggestions[i + 1].key}={suggestions[i + 1].value}, count={suggestions[i + 1].count})"
            )

    @given(scan_result=scan_result_with_tags(), prefix=prefix_strategy)
    @settings(max_examples=50, deadline=None)
    def test_suggestion_counts_are_positive(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """Every suggestion has a positive count (at least 1 occurrence).

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        for suggestion in suggestions:
            assert suggestion.count > 0, (
                f"Suggestion ({suggestion.key}={suggestion.value}) has "
                f"non-positive count: {suggestion.count}"
            )


class TestTagSuggestionsCountAccuracy:
    """Suggestion counts accurately reflect actual tag frequency."""

    @given(scan_result=scan_result_with_tags(), prefix=prefix_strategy)
    @settings(max_examples=50, deadline=None)
    def test_suggestion_count_matches_actual_frequency(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """Each suggestion's count equals the number of resources with that tag pair.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        # Compute actual frequency for each tag pair
        for suggestion in suggestions:
            actual_count = sum(
                1
                for r in scan_result.resources
                if r.tags.get(suggestion.key) == suggestion.value
            )
            assert suggestion.count == actual_count, (
                f"Suggestion ({suggestion.key}={suggestion.value}) reports "
                f"count={suggestion.count} but actual frequency is {actual_count}"
            )


class TestTagSuggestionsPrefixFiltering:
    """Prefix filtering narrows results correctly."""

    @given(scan_result=scan_result_with_tags(), prefix=prefix_strategy)
    @settings(max_examples=50, deadline=None)
    def test_all_suggestions_match_prefix(
        self, scan_result: ScanResult, prefix: str
    ) -> None:
        """Every returned suggestion has key or value starting with the prefix.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, prefix)

        if not prefix:
            return  # Empty prefix matches everything, nothing to assert

        prefix_lower = prefix.lower()
        for suggestion in suggestions:
            key_matches = suggestion.key.lower().startswith(prefix_lower)
            value_matches = suggestion.value.lower().startswith(prefix_lower)
            assert key_matches or value_matches, (
                f"Suggestion ({suggestion.key}={suggestion.value}) does not "
                f"match prefix '{prefix}' (case-insensitive)"
            )

    @given(scan_result=scan_result_with_tags())
    @settings(max_examples=50, deadline=None)
    def test_empty_prefix_returns_all_unique_pairs_up_to_20(
        self, scan_result: ScanResult
    ) -> None:
        """Empty prefix returns suggestions for all tag pairs (capped at 20).

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, "")

        # Count distinct tag pairs in the scan data
        distinct_pairs = set()
        for resource in scan_result.resources:
            for key, value in resource.tags.items():
                distinct_pairs.add((key, value))

        expected_count = min(len(distinct_pairs), 20)
        assert len(suggestions) == expected_count, (
            f"Expected {expected_count} suggestions for empty prefix "
            f"({len(distinct_pairs)} distinct pairs), got {len(suggestions)}"
        )


class TestTagSuggestionsTopFrequency:
    """The top-20 returned are genuinely the most frequent."""

    @given(scan_result=scan_result_with_tags())
    @settings(max_examples=50, deadline=None)
    def test_returned_suggestions_are_top_by_frequency(
        self, scan_result: ScanResult
    ) -> None:
        """No omitted tag pair has a higher frequency than any returned suggestion.

        **Validates: Requirements 7.2**
        """
        engine = FilterEngine()

        suggestions = engine.get_tag_suggestions(scan_result, "")

        if not suggestions:
            return

        # Compute actual frequencies for ALL tag pairs
        from collections import Counter

        tag_counter: Counter[tuple[str, str]] = Counter()
        for resource in scan_result.resources:
            for key, value in resource.tags.items():
                tag_counter[(key, value)] += 1

        # The minimum count in our returned set
        min_returned_count = suggestions[-1].count

        # All returned pairs
        returned_pairs = {(s.key, s.value) for s in suggestions}

        # Check no omitted pair has a higher frequency
        for (key, value), count in tag_counter.items():
            if (key, value) not in returned_pairs:
                assert count <= min_returned_count, (
                    f"Omitted tag pair ({key}={value}) with count={count} "
                    f"has higher frequency than minimum returned "
                    f"count={min_returned_count}"
                )
