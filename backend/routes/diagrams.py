"""API routes for diagram data retrieval and filtered views."""

import json
import logging
from urllib.parse import unquote

from fastapi import APIRouter, Query

from ..dependencies import filter_engine
from ..exceptions import CloudSpyglassError
from ..models.diagram import DiagramData
from ..models.filters import FilteredResult, TagFilter
from ..models.hierarchy import ContainerMetadata, HierarchyTree
from ..models.resources import Resource
from ..services.hierarchy_builder import HierarchyBuilder
from .scan import get_last_scan_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["diagrams"])


@router.get("/diagrams/latest", response_model=DiagramData)
async def get_latest_diagram() -> DiagramData:
    """Return the latest unfiltered diagram data from the most recent scan.

    Requirements: 5.1, 6.5
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    # Apply no filters to get full diagram
    result = filter_engine.apply_filters(scan_result)

    # Build hierarchy from full scan data (not filtered) for complete topology
    try:
        hierarchy_builder = HierarchyBuilder()
        hierarchy = hierarchy_builder.build(
            resources=scan_result.resources,
            relationships=scan_result.relationships,
            account_id=scan_result.account_id,
            scanned_regions=scan_result.scanned_regions,
        )
        result.diagram.hierarchy = hierarchy
    except Exception:
        logger.exception("Failed to build hierarchy tree")
        result.diagram.hierarchy = None

    return result.diagram


@router.get("/diagrams/latest/filtered", response_model=FilteredResult)
async def get_filtered_diagram(
    tag_filters: str | None = Query(
        default=None,
        description='JSON array of tag filters, e.g. [{"key":"env","value":"prod"}]',
    ),
    type_filters: str | None = Query(
        default=None,
        description="Comma-separated list of resource types to include",
    ),
    tag_filter_operator: str = Query(
        default="AND",
        description='Logic operator for tag filters: "AND" (match all) or "OR" (match any)',
    ),
) -> FilteredResult:
    """Return filtered diagram data based on tag and/or type criteria.

    Accepts FilterCriteria as query params:
    - tag_filters: JSON string of [{key, value}] objects (AND logic)
    - type_filters: Comma-separated resource type strings (OR logic)

    Requirements: 7.2, 5.1
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    # Parse tag_filters from JSON string
    parsed_tag_filters: list[TagFilter] = []
    if tag_filters:
        try:
            raw_tags = json.loads(tag_filters)
            if not isinstance(raw_tags, list):
                raise CloudSpyglassError(
                    error_code="INVALID_FILTER",
                    message="tag_filters must be a JSON array.",
                    recoverable=False,
                    status_code=400,
                )
            parsed_tag_filters = [TagFilter(**item) for item in raw_tags]
        except json.JSONDecodeError:
            raise CloudSpyglassError(
                error_code="INVALID_FILTER",
                message="tag_filters is not valid JSON.",
                recoverable=False,
                status_code=400,
            )
        except (TypeError, ValueError) as exc:
            raise CloudSpyglassError(
                error_code="INVALID_FILTER",
                message=f"Invalid tag filter format: {exc}",
                recoverable=False,
                status_code=400,
            )

    # Parse type_filters from JSON array or comma-separated string
    parsed_type_filters: list[str] = []
    if type_filters:
        # Try JSON array first (frontend sends ["type1","type2"])
        try:
            raw_types = json.loads(type_filters)
            if isinstance(raw_types, list):
                parsed_type_filters = [str(t).strip() for t in raw_types if str(t).strip()]
            else:
                # Not a list, treat as comma-separated
                parsed_type_filters = [t.strip() for t in type_filters.split(",") if t.strip()]
        except (json.JSONDecodeError, ValueError):
            # Fall back to comma-separated
            parsed_type_filters = [t.strip() for t in type_filters.split(",") if t.strip()]

    result = filter_engine.apply_filters(
        scan_result,
        tag_filters=parsed_tag_filters if parsed_tag_filters else None,
        type_filters=parsed_type_filters if parsed_type_filters else None,
        tag_filter_operator=tag_filter_operator.upper() if tag_filter_operator else "AND",
    )

    # Build hierarchy from full (unfiltered) scan data and prune to show only
    # containers that are ancestors of filtered resources. This keeps the
    # architecture diagram visible even when filters are active.
    try:
        hierarchy_builder = HierarchyBuilder()
        full_hierarchy = hierarchy_builder.build(
            resources=scan_result.resources,
            relationships=scan_result.relationships,
            account_id=scan_result.account_id,
            scanned_regions=scan_result.scanned_regions,
        )
        # Prune hierarchy: keep only containers with matching resources
        filtered_node_ids = {node.id for node in result.diagram.nodes}
        pruned_hierarchy = _prune_hierarchy(full_hierarchy, filtered_node_ids)
        result.diagram.hierarchy = pruned_hierarchy
    except Exception:
        logger.exception("Failed to build hierarchy tree for filtered diagram")
        result.diagram.hierarchy = None

    return result


def _prune_hierarchy(
    hierarchy: HierarchyTree, filtered_resource_ids: set[str]
) -> HierarchyTree | None:
    """Prune a hierarchy tree to keep only containers that are ancestors of filtered resources.

    A container is kept if:
    - It has at least one filtered resource directly assigned, OR
    - It has a descendant container that contains filtered resources (ancestor path)

    Containers with zero matching resources (recursively) are removed.
    Container `resources` arrays are filtered to only include matching IDs.
    Container `children` arrays are updated to only reference kept children.
    Boundary services are kept only if their resource_arn is in the filtered set.

    Returns None if no containers would remain after pruning.
    """
    if not hierarchy or not hierarchy.containers:
        return None

    # Build lookup maps
    container_map: dict[str, ContainerMetadata] = {
        c.id: c for c in hierarchy.containers
    }

    # Determine which containers have filtered resources (directly or recursively)
    containers_with_resources: set[str] = set()

    def _has_filtered_resources(container_id: str) -> bool:
        """Recursively check if a container or any descendant has filtered resources."""
        container = container_map.get(container_id)
        if not container:
            return False

        # Check direct resources
        if any(r in filtered_resource_ids for r in container.resources):
            containers_with_resources.add(container_id)
            return True

        # Check children recursively
        for child_id in container.children:
            if _has_filtered_resources(child_id):
                containers_with_resources.add(container_id)
                return True

        return False

    # Start from root
    _has_filtered_resources(hierarchy.root_id)

    # If no containers have resources, return None (will fall back to dagre)
    if not containers_with_resources:
        return None

    # Build pruned containers list
    pruned_containers: list[ContainerMetadata] = []
    for container in hierarchy.containers:
        if container.id not in containers_with_resources:
            continue

        # Filter resources to only include matching ones
        filtered_resources = [
            r for r in container.resources if r in filtered_resource_ids
        ]

        # Filter children to only include kept ones
        filtered_children = [
            c for c in container.children if c in containers_with_resources
        ]

        pruned_containers.append(
            ContainerMetadata(
                id=container.id,
                name=container.name,
                type=container.type,
                parent_id=container.parent_id,
                subnet_type=container.subnet_type,
                icon_key=container.icon_key,
                resources=filtered_resources,
                children=filtered_children,
            )
        )

    # Filter boundary services to only include those whose resource is in the filtered set
    pruned_boundary_services = [
        bs
        for bs in hierarchy.boundary_services
        if bs.resource_arn in filtered_resource_ids
        and bs.inner_container_id in containers_with_resources
    ]

    return HierarchyTree(
        containers=pruned_containers,
        root_id=hierarchy.root_id,
        boundary_services=pruned_boundary_services,
    )


@router.get("/resources/{resource_id:path}", response_model=Resource)
async def get_resource_detail(resource_id: str) -> Resource:
    """Return full resource metadata for a given resource ARN.

    Looks up the resource from the latest scan result.
    The resource_id is the ARN (URL-encoded in the path).
    """
    scan_result = get_last_scan_result()
    if scan_result is None:
        raise CloudSpyglassError(
            error_code="NO_SCAN_DATA",
            message="No scan data available. Please run a scan first.",
            recoverable=True,
            status_code=404,
        )

    decoded_id = unquote(resource_id)
    for resource in scan_result.resources:
        if resource.arn == decoded_id:
            return resource

    raise CloudSpyglassError(
        error_code="RESOURCE_NOT_FOUND",
        message=f"Resource not found: {decoded_id}",
        recoverable=False,
        status_code=404,
    )
