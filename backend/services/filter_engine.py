"""Server-side filtering with tag autocomplete support."""

import hashlib
import logging
from collections import Counter

from ..models.diagram import DiagramData, DiagramEdge, DiagramNode
from ..models.filters import FilterCriteria, FilteredResult, TagFilter, TagSuggestion
from ..models.scan import ScanResult

logger = logging.getLogger(__name__)


class FilterEngine:
    """Server-side filtering with tag autocomplete support.

    Applies tag-based and resource-type-based filters to scan results,
    producing filtered diagram data suitable for frontend rendering.

    Filter logic:
    - Tag filters use AND logic: a resource must match ALL tag criteria.
    - Type filters use OR logic: a resource must match ANY selected type.
    - Combined: intersection of tag AND type filters.

    Edge filtering:
    - Tag-filtered edges: both endpoints must be in the filtered set.
    - Type-filtered edges: at least one endpoint must be in the filtered set.
    - Combined: both endpoints must pass the combined filter.
    """

    def apply_filters(
        self,
        scan_result: ScanResult,
        tag_filters: list[TagFilter] | None = None,
        type_filters: list[str] | None = None,
    ) -> FilteredResult:
        """Apply tag and/or resource-type filters to a scan result.

        Args:
            scan_result: The full scan result containing resources and relationships.
            tag_filters: Optional list of tag key-value pairs (AND logic).
            type_filters: Optional list of resource type strings (OR logic).

        Returns:
            FilteredResult containing the filtered diagram data, counts, and
            active filter criteria.
        """
        tag_filters = tag_filters or []
        type_filters = type_filters or []

        resources = scan_result.resources
        relationships = scan_result.relationships
        total_count = len(resources)

        # Determine which filter mode we're in
        has_tag_filters = len(tag_filters) > 0
        has_type_filters = len(type_filters) > 0

        if has_tag_filters and has_type_filters:
            # Combined: intersection of tag AND type filters
            filtered_arns = self._apply_combined_filters(
                resources, tag_filters, type_filters
            )
            # Combined uses tag-filter edge logic: both endpoints must match
            filtered_edges = self._filter_edges_both_endpoints(
                relationships, filtered_arns
            )
        elif has_tag_filters:
            # Tag-only: AND logic, edges require both endpoints
            filtered_arns = self._apply_tag_filters(resources, tag_filters)
            filtered_edges = self._filter_edges_both_endpoints(
                relationships, filtered_arns
            )
        elif has_type_filters:
            # Type-only: OR logic, edges require at least one endpoint
            filtered_arns = self._apply_type_filters(resources, type_filters)
            filtered_edges = self._filter_edges_at_least_one_endpoint(
                relationships, filtered_arns
            )
        else:
            # No filters: return everything
            filtered_arns = {r.arn for r in resources}
            filtered_edges = relationships

        # Build filtered resource lookup
        resource_map = {r.arn: r for r in resources}
        filtered_resources = [
            resource_map[arn] for arn in filtered_arns if arn in resource_map
        ]

        # Convert to diagram data
        nodes = [self._resource_to_node(r) for r in filtered_resources]
        edges = [self._relationship_to_edge(rel) for rel in filtered_edges]

        diagram = DiagramData(
            nodes=nodes,
            edges=edges,
            account_id=scan_result.account_id,
            scan_timestamp=scan_result.scan_timestamp,
            total_resources=total_count,
            scanned_regions=scan_result.scanned_regions,
            failures=scan_result.failures,
        )

        active_filters = FilterCriteria(
            tag_filters=tag_filters,
            type_filters=type_filters,
        )

        return FilteredResult(
            diagram=diagram,
            filtered_count=len(filtered_resources),
            total_count=total_count,
            active_filters=active_filters,
        )

    def get_tag_suggestions(
        self, scan_result: ScanResult, prefix: str
    ) -> list[TagSuggestion]:
        """Return top 20 tag key-value pairs by descending frequency.

        Filters suggestions by a prefix that can match against either the
        tag key or the tag value (case-insensitive).

        Args:
            scan_result: The full scan result containing resources.
            prefix: A prefix string to filter suggestions (matches key or value).

        Returns:
            List of up to 20 TagSuggestion objects ordered by descending count.
        """
        # Count frequency of each (key, value) pair across all resources
        tag_counter: Counter[tuple[str, str]] = Counter()

        for resource in scan_result.resources:
            for key, value in resource.tags.items():
                tag_counter[(key, value)] += 1

        # Filter by prefix (case-insensitive match on key or value)
        prefix_lower = prefix.lower()
        if prefix_lower:
            filtered_tags = {
                kv: count
                for kv, count in tag_counter.items()
                if kv[0].lower().startswith(prefix_lower)
                or kv[1].lower().startswith(prefix_lower)
            }
        else:
            filtered_tags = dict(tag_counter)

        # Sort by descending frequency, then alphabetically by key+value for stability
        sorted_tags = sorted(
            filtered_tags.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )

        # Return top 20
        return [
            TagSuggestion(key=kv[0], value=kv[1], count=count)
            for kv, count in sorted_tags[:20]
        ]

    # ------------------------------------------------------------------
    # Internal filter application methods
    # ------------------------------------------------------------------

    def _apply_tag_filters(
        self, resources: list, tag_filters: list[TagFilter]
    ) -> set[str]:
        """Apply AND logic: resource must match ALL tag filters.

        A resource matches a tag filter if it has a tag with the exact key
        and the exact value specified in the filter.
        """
        filtered_arns: set[str] = set()

        for resource in resources:
            if self._resource_matches_all_tags(resource, tag_filters):
                filtered_arns.add(resource.arn)

        return filtered_arns

    def _apply_type_filters(
        self, resources: list, type_filters: list[str]
    ) -> set[str]:
        """Apply OR logic: resource must match ANY selected type."""
        type_set = set(type_filters)
        return {r.arn for r in resources if r.resource_type in type_set}

    def _apply_combined_filters(
        self,
        resources: list,
        tag_filters: list[TagFilter],
        type_filters: list[str],
    ) -> set[str]:
        """Apply intersection: must match ALL tags AND at least one type."""
        type_set = set(type_filters)
        filtered_arns: set[str] = set()

        for resource in resources:
            if (
                resource.resource_type in type_set
                and self._resource_matches_all_tags(resource, tag_filters)
            ):
                filtered_arns.add(resource.arn)

        return filtered_arns

    def _resource_matches_all_tags(
        self, resource, tag_filters: list[TagFilter]
    ) -> bool:
        """Check if a resource matches all tag filter criteria (AND logic)."""
        for tf in tag_filters:
            if resource.tags.get(tf.key) != tf.value:
                return False
        return True

    # ------------------------------------------------------------------
    # Edge filtering methods
    # ------------------------------------------------------------------

    def _filter_edges_both_endpoints(
        self, relationships: list, filtered_arns: set[str]
    ) -> list:
        """Keep edges where BOTH source and target are in the filtered set.

        Used for tag-only and combined filters.
        """
        return [
            rel
            for rel in relationships
            if rel.source_arn in filtered_arns and rel.target_arn in filtered_arns
        ]

    def _filter_edges_at_least_one_endpoint(
        self, relationships: list, filtered_arns: set[str]
    ) -> list:
        """Keep edges where at least one endpoint is in the filtered set.

        Used for type-only filters.
        """
        return [
            rel
            for rel in relationships
            if rel.source_arn in filtered_arns or rel.target_arn in filtered_arns
        ]

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _resource_to_node(self, resource) -> DiagramNode:
        """Convert a Resource model to a DiagramNode."""
        return DiagramNode(
            id=resource.arn,
            resource_type=resource.resource_type,
            name=resource.name,
            region=resource.region,
            is_external=resource.is_external,
            is_unresolved=resource.is_unresolved,
            icon_url=f"/api/images/icons/{resource.resource_type}",
        )

    def _relationship_to_edge(self, relationship) -> DiagramEdge:
        """Convert a Relationship model to a DiagramEdge."""
        # Generate a stable edge ID from source + target ARNs
        edge_hash = hashlib.md5(
            f"{relationship.source_arn}:{relationship.target_arn}".encode()
        ).hexdigest()[:12]

        return DiagramEdge(
            id=edge_hash,
            source=relationship.source_arn,
            target=relationship.target_arn,
            category=relationship.category,
            derived_from=relationship.derived_from,
            label=None,
        )
