"""Property-based tests for filtered export annotation.

**Validates: Requirements 11.2**

Property 27: Filtered export annotation
- Test that exports with active filters contain only filtered resources and include
  filter annotation.
- WHEN filters are active during export, THE Export_Service SHALL export only the
  filtered view and include the active filter criteria as a text annotation in the
  header or footer area of the exported document.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.diagram import DiagramData, DiagramEdge, DiagramNode
from backend.models.export import ExportFormat
from backend.models.filters import FilterCriteria, TagFilter
from backend.services.export_service import ExportService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

RESOURCE_TYPES = ["ec2", "lambda", "s3", "rds", "alb", "nlb", "sqs", "sns", "ecs", "dynamodb"]

VALID_AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-central-1",
]

# Simple ASCII characters for tag keys/values to avoid XML escaping edge cases
tag_key_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=1,
    max_size=20,
)

tag_value_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=1,
    max_size=30,
)

region_strategy = st.sampled_from(VALID_AWS_REGIONS)
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)
account_id_strategy = st.text(alphabet="0123456789", min_size=12, max_size=12)

# Export formats for annotation testing (SVG and PDF have text-based annotations)
svg_pdf_format_strategy = st.sampled_from([ExportFormat.SVG, ExportFormat.PDF])
all_format_strategy = st.sampled_from([ExportFormat.SVG, ExportFormat.PDF, ExportFormat.PNG])


@st.composite
def tag_filter_strategy(draw):
    """Generate a non-empty list of TagFilter objects."""
    num_filters = draw(st.integers(min_value=1, max_value=5))
    filters = []
    seen_keys = set()
    for _ in range(num_filters):
        key = draw(tag_key_strategy.filter(lambda k: k not in seen_keys))
        seen_keys.add(key)
        value = draw(tag_value_strategy)
        filters.append(TagFilter(key=key, value=value))
    return filters


@st.composite
def type_filter_strategy(draw):
    """Generate a non-empty list of resource type filter strings."""
    num_filters = draw(st.integers(min_value=1, max_value=5))
    return draw(
        st.lists(
            resource_type_strategy,
            min_size=num_filters,
            max_size=num_filters,
            unique=True,
        )
    )


@st.composite
def active_filter_criteria_strategy(draw):
    """Generate a FilterCriteria with at least one active filter (tags and/or types)."""
    has_tags = draw(st.booleans())
    has_types = draw(st.booleans())

    # Ensure at least one is active
    if not has_tags and not has_types:
        has_tags = True

    tag_filters = draw(tag_filter_strategy()) if has_tags else []
    type_filters = draw(type_filter_strategy()) if has_types else []

    return FilterCriteria(tag_filters=tag_filters, type_filters=type_filters)


@st.composite
def empty_filter_criteria_strategy(draw):
    """Generate an empty or None FilterCriteria (no active filters)."""
    use_none = draw(st.booleans())
    if use_none:
        return None
    return FilterCriteria(tag_filters=[], type_filters=[])


@st.composite
def diagram_data_strategy(draw):
    """Generate a minimal valid DiagramData for export testing."""
    account_id = draw(account_id_strategy)
    num_nodes = draw(st.integers(min_value=1, max_value=8))
    region = draw(region_strategy)

    nodes = []
    for i in range(num_nodes):
        rtype = draw(resource_type_strategy)
        nodes.append(
            DiagramNode(
                id=f"arn:aws:{rtype}:{region}:{account_id}:resource/res-{i:04d}",
                resource_type=rtype,
                name=f"resource-{i}",
                region=region,
                icon_url=f"/api/images/icons/{rtype}",
            )
        )

    # Generate a few edges between existing nodes
    edges = []
    if len(nodes) >= 2:
        num_edges = draw(st.integers(min_value=0, max_value=min(4, len(nodes) - 1)))
        categories = ["network", "iam", "event", "data"]
        for j in range(num_edges):
            src_idx = draw(st.integers(min_value=0, max_value=len(nodes) - 2))
            tgt_idx = draw(st.integers(min_value=src_idx + 1, max_value=len(nodes) - 1))
            cat = draw(st.sampled_from(categories))
            edges.append(
                DiagramEdge(
                    id=f"edge-{j}",
                    source=nodes[src_idx].id,
                    target=nodes[tgt_idx].id,
                    category=cat,
                    derived_from="TestAttr",
                )
            )

    return DiagramData(
        nodes=nodes,
        edges=edges,
        account_id=account_id,
        scan_timestamp="2024-01-15T10:30:00Z",
        total_resources=num_nodes,
        scanned_regions=[region],
    )


# ---------------------------------------------------------------------------
# Property Tests: Active filters produce annotation in export content
# ---------------------------------------------------------------------------


class TestFilteredExportContainsAnnotation:
    """When filters are active, the exported content MUST contain the filter annotation."""

    @given(
        diagram_data=diagram_data_strategy(),
        filters=active_filter_criteria_strategy(),
        fmt=svg_pdf_format_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_active_filters_produce_annotation_in_svg_and_pdf(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria,
        fmt: ExportFormat,
    ) -> None:
        """For ANY export with active filters, the output MUST contain filter annotation text.

        - SVG: contains "Filters:" text with the criteria
        - PDF: contains "Active Filters:" line with the criteria

        **Validates: Requirements 11.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ExportService(export_dir=Path(tmp_dir))
            result = await service.export(diagram_data, fmt, filters)

            # Read the exported file content
            exported_path = Path(result.path)
            content = exported_path.read_bytes().decode("utf-8", errors="replace")

            if fmt == ExportFormat.SVG:
                assert "Filters:" in content, (
                    f"SVG export with active filters must contain 'Filters:' annotation. "
                    f"Filters: tag_filters={filters.tag_filters}, type_filters={filters.type_filters}"
                )
            elif fmt == ExportFormat.PDF:
                assert "Active Filters:" in content, (
                    f"PDF export with active filters must contain 'Active Filters:' annotation. "
                    f"Filters: tag_filters={filters.tag_filters}, type_filters={filters.type_filters}"
                )


# ---------------------------------------------------------------------------
# Property Tests: No annotation when filters are inactive
# ---------------------------------------------------------------------------


class TestNoAnnotationWithoutActiveFilters:
    """When filters are NOT active, the export MUST NOT contain filter annotation text."""

    @given(
        diagram_data=diagram_data_strategy(),
        filters=empty_filter_criteria_strategy(),
        fmt=svg_pdf_format_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_no_annotation_without_active_filters(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria | None,
        fmt: ExportFormat,
    ) -> None:
        """For ANY export WITHOUT active filters, no annotation appears.

        **Validates: Requirements 11.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ExportService(export_dir=Path(tmp_dir))
            result = await service.export(diagram_data, fmt, filters)

            exported_path = Path(result.path)
            content = exported_path.read_bytes().decode("utf-8", errors="replace")

            if fmt == ExportFormat.SVG:
                assert "Filters:" not in content, (
                    "SVG export without active filters must NOT contain 'Filters:' annotation."
                )
            elif fmt == ExportFormat.PDF:
                assert "Active Filters:" not in content, (
                    "PDF export without active filters must NOT contain 'Active Filters:' annotation."
                )


# ---------------------------------------------------------------------------
# Property Tests: Annotation includes ALL tag filter key-value pairs
# ---------------------------------------------------------------------------


class TestAnnotationIncludesAllTagFilters:
    """The annotation MUST include ALL active tag filter key=value pairs."""

    @given(
        diagram_data=diagram_data_strategy(),
        tag_filters=tag_filter_strategy(),
        fmt=svg_pdf_format_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_all_tag_filters_appear_in_annotation(
        self,
        diagram_data: DiagramData,
        tag_filters: list[TagFilter],
        fmt: ExportFormat,
    ) -> None:
        """For ANY set of tag_filters, each key=value pair appears in the annotation.

        **Validates: Requirements 11.2**
        """
        filters = FilterCriteria(tag_filters=tag_filters, type_filters=[])

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ExportService(export_dir=Path(tmp_dir))
            result = await service.export(diagram_data, fmt, filters)

            exported_path = Path(result.path)
            content = exported_path.read_bytes().decode("utf-8", errors="replace")

            for tf in tag_filters:
                expected_pair = f"{tf.key}={tf.value}"
                assert expected_pair in content, (
                    f"Export annotation must include tag filter '{expected_pair}'. "
                    f"Format: {fmt.value}, content snippet: {content[:500]}"
                )


# ---------------------------------------------------------------------------
# Property Tests: Annotation includes ALL type filter values
# ---------------------------------------------------------------------------


class TestAnnotationIncludesAllTypeFilters:
    """The annotation MUST include ALL active type filter values."""

    @given(
        diagram_data=diagram_data_strategy(),
        type_filters=type_filter_strategy(),
        fmt=svg_pdf_format_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_all_type_filters_appear_in_annotation(
        self,
        diagram_data: DiagramData,
        type_filters: list[str],
        fmt: ExportFormat,
    ) -> None:
        """For ANY set of type_filters, each type name appears in the annotation.

        **Validates: Requirements 11.2**
        """
        filters = FilterCriteria(tag_filters=[], type_filters=type_filters)

        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ExportService(export_dir=Path(tmp_dir))
            result = await service.export(diagram_data, fmt, filters)

            exported_path = Path(result.path)
            content = exported_path.read_bytes().decode("utf-8", errors="replace")

            for type_name in type_filters:
                assert type_name in content, (
                    f"Export annotation must include type filter '{type_name}'. "
                    f"Format: {fmt.value}, content snippet: {content[:500]}"
                )


# ---------------------------------------------------------------------------
# Property Tests: Export renders exactly the diagram data passed to it
# ---------------------------------------------------------------------------


class TestExportRendersOnlyProvidedData:
    """The export renders exactly the diagram data that is passed (filtered view)."""

    @given(
        diagram_data=diagram_data_strategy(),
        filters=active_filter_criteria_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    async def test_svg_export_contains_only_provided_nodes(
        self,
        diagram_data: DiagramData,
        filters: FilterCriteria,
    ) -> None:
        """The SVG export contains exactly the nodes from the diagram_data passed in.

        This validates that the export service renders exactly what it's given - the
        filtered view - without adding or removing resources.

        **Validates: Requirements 11.2**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = ExportService(export_dir=Path(tmp_dir))
            result = await service.export(diagram_data, ExportFormat.SVG, filters)

            exported_path = Path(result.path)
            content = exported_path.read_bytes().decode("utf-8")

            # Each node's name should appear in the SVG
            for node in diagram_data.nodes:
                # Node names are truncated to 22 chars in the SVG renderer
                expected_name = node.name[:22]
                assert expected_name in content, (
                    f"SVG export must contain node name '{expected_name}' from diagram data."
                )
