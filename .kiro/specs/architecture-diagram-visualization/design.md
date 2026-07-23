# Design Document: Architecture Diagram Visualization

## Overview

This design replaces the current flat dagre-based flowchart with a nested, hierarchical AWS architecture diagram that mirrors official AWS architecture diagram conventions. The key transformation is moving from a flat node-edge graph to a container-based spatial layout where resources are visually grouped inside their network boundaries (VPC → AZ → Subnet) with official AWS icons, color-coded relationship arrows, and interactive collapse/expand behavior.

The implementation spans both backend (new `HierarchyBuilder` service producing a pre-computed tree) and frontend (new container node types, hierarchical layout engine, boundary service positioning, and viewport performance optimizations).

### Design Decisions

1. **Backend pre-computation over frontend computation**: The hierarchy tree is built server-side to avoid expensive re-computation on every render and keep the frontend focused on layout/rendering.
2. **Extend existing API rather than new endpoints**: The hierarchy data is added as a new field on the existing `/api/diagrams/latest` response to maintain backward compatibility.
3. **React Flow nested groups**: Leverage React Flow's built-in `parentId` mechanism for nested container nodes rather than implementing custom DOM nesting.
4. **Dagre replaced by custom hierarchical layout**: The existing dagre auto-layout is replaced with a recursive container-aware layout algorithm that respects parent-child spatial constraints.
5. **SVG icons served via existing `/api/images/icons/` route**: Icons continue to be served from the backend, with new mappings for group icons and the 48px service icon size.

## Architecture

```mermaid
graph TD
    subgraph Backend
        A[Scanner] --> B[RelationshipResolver]
        B --> C[HierarchyBuilder - NEW]
        C --> D[DiagramData + HierarchyTree]
        D --> E[/api/diagrams/latest]
    end

    subgraph Frontend
        E --> F[useDiagramData hook]
        F --> G[HierarchyLayoutEngine - NEW]
        G --> H[ContainerNode - NEW]
        G --> I[ResourceNode - UPDATED]
        G --> J[BoundaryServiceNode - NEW]
        G --> K[EdgeRenderer - UPDATED]
        H --> L[ReactFlow Canvas]
        I --> L
        J --> L
        K --> L
    end
```

### Data Flow

1. **Scan** → `Scanner` discovers resources and their attributes (vpc_id, subnet_id, availability_zone, etc.)
2. **Relationships** → `RelationshipResolver` detects connections between resources (unchanged)
3. **Hierarchy** → `HierarchyBuilder` (new) transforms flat resources into a container tree: cloud → account → region → vpc → az → subnet, classifying each resource into the deepest matching container
4. **API Response** → Existing `DiagramData` response is extended with a `hierarchy` field containing the container tree
5. **Layout** → Frontend `HierarchyLayoutEngine` computes spatial positions recursively: parent containers size themselves based on children, then position children with grid/flow sub-layout
6. **Render** → React Flow renders container nodes (with `parentId` linkage), resource nodes placed inside containers, edges routed between them

## Components and Interfaces

### Backend Components

#### HierarchyBuilder Service (`backend/services/hierarchy_builder.py`)

Transforms flat resource data into a nested container tree.

```python
class HierarchyBuilder:
    """Builds the AWS infrastructure hierarchy from flat resource data."""

    GLOBAL_SERVICES = {"iam", "route53", "cloudfront", "s3", "waf"}
    BOUNDARY_SERVICES = {"internet_gateway", "nat_gateway", "waf", "vpn_gateway"}

    def build(
        self,
        resources: list[Resource],
        relationships: list[Relationship],
        account_id: str,
        scanned_regions: list[str],
    ) -> HierarchyTree:
        """Build complete hierarchy tree from scan data."""
        ...

    def _classify_subnet_type(
        self, subnet_resource: Resource, resources: list[Resource]
    ) -> Literal["public", "private"]:
        """Determine if subnet is public or private based on route tables."""
        ...

    def _assign_resource_to_container(
        self, resource: Resource, tree: HierarchyTree
    ) -> str:
        """Return the container_id for the deepest container this resource belongs to."""
        ...
```

#### Architecture Icon Resolver (`backend/services/icon_resolver.py`)

Maps resource types and container types to SVG icon file paths.

```python
class ArchitectureIconResolver:
    """Maps AWS resource types to their official architecture icon paths."""

    SERVICE_ICON_BASE = "assets/icons/Architecture-Service-Icons_07312025"
    GROUP_ICON_BASE = "assets/icons/Architecture-Group-Icons_07312025"

    def resolve_service_icon(self, resource_type: str) -> str:
        """Return URL path to the 48px SVG icon for a service type."""
        ...

    def resolve_group_icon(self, container_type: str) -> str:
        """Return URL path to the 32px SVG group icon for a container type."""
        ...
```

### Frontend Components

#### ContainerNode (`frontend/src/components/ContainerNode.tsx`)

A custom React Flow node type that renders a styled, labeled container with icon badge.

```typescript
interface ContainerNodeData {
  label: string;
  containerType: 'cloud' | 'account' | 'region' | 'vpc' | 'az' | 'subnet';
  subnetType?: 'public' | 'private';
  iconUrl: string;
  isCollapsed: boolean;
  resourceCount: number;
}
```

#### BoundaryServiceNode (`frontend/src/components/BoundaryServiceNode.tsx`)

A specialized node for IGW, NAT Gateway, WAF, VPN Gateway positioned at container edges.

```typescript
interface BoundaryServiceNodeData {
  label: string;
  resourceType: string;
  iconUrl: string;
  boundaryType: 'igw' | 'nat' | 'waf' | 'vpn';
}
```

#### HierarchyLayoutEngine (`frontend/src/layout/HierarchyLayoutEngine.ts`)

Replaces dagre with a recursive hierarchical layout algorithm.

```typescript
interface LayoutOptions {
  containerPadding: number;      // 20px min
  resourceSpacing: number;       // 16px min
  boundaryServiceGap: number;    // 20px min between adjacent boundary services
  minContainerWidth: number;     // 100px
  minContainerHeight: number;    // 60px
}

interface LayoutResult {
  nodes: Node[];                 // Positioned React Flow nodes (containers + resources)
  edges: Edge[];                 // Styled React Flow edges
}

function computeHierarchyLayout(
  hierarchy: HierarchyTree,
  diagramNodes: DiagramNode[],
  diagramEdges: DiagramEdge[],
  options?: Partial<LayoutOptions>
): LayoutResult;
```

#### Updated DiagramCanvas (`frontend/src/components/DiagramCanvas.tsx`)

Orchestrates the new layout and manages container collapse/expand state.

Key changes:
- Replaces `applyDagreLayout` with `computeHierarchyLayout`
- Registers `ContainerNode` and `BoundaryServiceNode` as additional node types
- Manages collapsed container state via `useState<Set<string>>`
- Implements hover highlight/dim for edges
- Implements viewport culling for large diagrams (>200 resources)
- Auto-collapses deep containers when >50 containers present

#### ExternalResourcesContainer (`frontend/src/components/ExternalResourcesContainer.tsx`)

Renders the external resources area with sub-grouping by category.

```typescript
interface ExternalGroup {
  category: 'cross_account' | 'on_premises' | 'third_party' | 'unknown';
  resources: DiagramNode[];
}
```

## Data Models

### Backend Models (Pydantic)

#### New: `backend/models/hierarchy.py`

```python
from typing import Literal
from pydantic import BaseModel


class ContainerMetadata(BaseModel):
    """Metadata for a single container in the hierarchy tree."""
    id: str                                         # Unique container ID (e.g., "vpc-abc123")
    name: str                                       # Display label
    type: Literal["cloud", "account", "region", "vpc", "az", "subnet"]
    parent_id: str | None = None                    # Parent container ID (None for root)
    subnet_type: Literal["public", "private"] | None = None  # Only for subnet containers
    icon_key: str                                   # Key for icon resolver
    resources: list[str] = []                       # Resource ARNs assigned to this container
    children: list[str] = []                        # Child container IDs


class HierarchyTree(BaseModel):
    """Pre-computed hierarchy tree for the architecture diagram."""
    containers: list[ContainerMetadata]
    root_id: str                                    # ID of the top-level "cloud" container
    boundary_services: list[BoundaryServicePlacement] = []


class BoundaryServicePlacement(BaseModel):
    """Positioning hint for a boundary service."""
    resource_arn: str
    boundary_type: Literal["igw", "nat", "waf", "vpn"]
    inner_container_id: str                         # Container the service is "inside"
    outer_container_id: str | None = None           # Container the service is "outside" (None if N/A)
    edge_position: Literal["top", "bottom", "left", "right"] = "top"
```

#### Updated: `backend/models/diagram.py`

```python
class DiagramData(BaseModel):
    """Complete diagram payload sent to the frontend."""
    nodes: list[DiagramNode]
    edges: list[DiagramEdge]
    account_id: str
    scan_timestamp: str
    total_resources: int
    scanned_regions: list[str]
    failures: list[RegionFailure] = []
    hierarchy: HierarchyTree | None = None          # NEW: pre-computed hierarchy
```

### Frontend Types (TypeScript)

#### New: `frontend/src/types/hierarchy.ts`

```typescript
export type ContainerType = 'cloud' | 'account' | 'region' | 'vpc' | 'az' | 'subnet';
export type SubnetType = 'public' | 'private';
export type BoundaryType = 'igw' | 'nat' | 'waf' | 'vpn';
export type EdgePosition = 'top' | 'bottom' | 'left' | 'right';

export interface ContainerMetadata {
  id: string;
  name: string;
  type: ContainerType;
  parent_id: string | null;
  subnet_type: SubnetType | null;
  icon_key: string;
  resources: string[];
  children: string[];
}

export interface BoundaryServicePlacement {
  resource_arn: string;
  boundary_type: BoundaryType;
  inner_container_id: string;
  outer_container_id: string | null;
  edge_position: EdgePosition;
}

export interface HierarchyTree {
  containers: ContainerMetadata[];
  root_id: string;
  boundary_services: BoundaryServicePlacement[];
}
```

#### Updated: `frontend/src/types/diagram.ts`

```typescript
import type { HierarchyTree } from './hierarchy';

export interface DiagramData {
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  account_id: string;
  scan_timestamp: string;
  total_resources: number;
  scanned_regions: string[];
  failures: RegionFailure[];
  hierarchy: HierarchyTree | null;  // NEW
}
```

### Container Styling Map

| Container Type | Border | Background | Border Style |
|---|---|---|---|
| AWS Cloud | 2px #232F3E | rgba(240, 240, 240, 0.5) | dashed |
| Account | 2px #DF3312 | transparent | dashed |
| Region | 2px #147EB4 | rgba(20, 126, 180, 0.05) | dashed |
| VPC | 2px #1B660F | rgba(27, 102, 15, 0.05) | solid |
| AZ | 1px #5A6B7B | transparent | dashed |
| Public Subnet | 2px #1B660F | rgba(27, 102, 15, 0.15) | solid |
| Private Subnet | 2px #147EB4 | rgba(20, 126, 180, 0.15) | solid |

### Edge Styling Map

| Category | Color | Line Style |
|---|---|---|
| network | #2563EB (blue) | solid |
| iam | #DC2626 (red) | dashed (5,5) |
| event | #EA580C (orange) | dotted (2,2) |
| data | #7C3AED (purple) | solid |
| unknown/other | #6B7280 (gray) | solid |



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Hierarchy Nesting Order

*For any* valid scan data containing resources with account IDs, regions, VPCs, availability zones, and subnets, the `HierarchyBuilder` output SHALL produce a tree where every container's parent type follows the strict ordering: cloud → account → region → vpc → az → subnet (i.e., no container has a parent of a type that should be a descendant in the hierarchy).

**Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6, 6.1**

### Property 2: Subnet Classification Correctness

*For any* subnet resource, the `HierarchyBuilder` SHALL classify it as "public" if and only if its associated route table contains a route with a destination of `0.0.0.0/0` targeting an Internet Gateway; otherwise it SHALL classify the subnet as "private".

**Validates: Requirements 1.7, 1.8, 6.3**

### Property 3: Resource Placement Priority

*For any* resource, the `HierarchyBuilder` SHALL assign it to exactly one container determined by the first matching rule in priority order: (1) is_external → outside cloud, (2) global service type → account container, (3) has subnet_id → subnet container, (4) has vpc_id + availability_zone → AZ container, (5) has vpc_id only → VPC container, (6) otherwise → region container. No resource shall appear in more than one container, and no resource shall be unassigned.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.2, 6.7**

### Property 4: No Sibling Overlap in Layout

*For any* layout result, no two sibling nodes (resource nodes or sub-containers sharing the same parent container) SHALL have overlapping bounding boxes.

**Validates: Requirements 1.9, 3.8**

### Property 5: Minimum Parent Padding

*For any* container in the layout result that has children, every child node's bounding box SHALL be at least 20 pixels from the parent container's border on all sides.

**Validates: Requirements 1.10**

### Property 6: Minimum Container Dimensions

*For any* container in the layout result that has no children (no resources and no sub-containers), its rendered width SHALL be at least 100 pixels and its rendered height SHALL be at least 60 pixels.

**Validates: Requirements 1.11**

### Property 7: Edge Category-to-Style Mapping

*For any* diagram edge, the rendered style (color and line pattern) SHALL be deterministically determined by its category: "network" → blue/solid, "iam" → red/dashed, "event" → orange/dotted, "data" → purple/solid, and any other category → gray/solid. No edge shall have a style that disagrees with its category.

**Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.9**

### Property 8: Edge Label Truncation

*For any* edge label string, if its length exceeds 40 characters the displayed text SHALL be the first 40 characters followed by "…" (total displayed length 41); if its length is 40 or fewer characters the full text SHALL be displayed unmodified.

**Validates: Requirements 4.6**

### Property 9: Edge Count Matches Relationships

*For any* set of relationships provided to the diagram, the rendered edge set SHALL contain exactly one directed edge per relationship, with source and target matching the relationship's source_arn and target_arn respectively.

**Validates: Requirements 4.1**

### Property 10: Boundary Service Positioning

*For any* boundary service (internet_gateway, nat_gateway, waf, vpn_gateway) in the layout, the node's center coordinates SHALL lie on the border line of its designated container edge, resulting in approximately 50% of the node area inside and 50% outside the container boundary.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 11: Boundary Service Spacing

*For any* container edge that has multiple boundary service nodes positioned on it, the horizontal distance between the edges of adjacent boundary service nodes SHALL be at least 20 pixels.

**Validates: Requirements 5.7**

### Property 12: Container Metadata Completeness

*For any* container produced by the `HierarchyBuilder`, it SHALL have all required fields populated: a non-empty `id`, a non-empty `name`, a valid `type` from the set {cloud, account, region, vpc, az, subnet}, a `parent_id` (null only for root), an `icon_key`, and a `resources` array (which may be empty).

**Validates: Requirements 6.6**

### Property 13: Collapsed Container Badge Count

*For any* collapsed container, the displayed resource count badge SHALL equal the total number of resource nodes recursively contained within that container and all its nested sub-containers.

**Validates: Requirements 8.4**

### Property 14: Edge Rerouting on Collapse

*For any* collapsed container that contains resources which are sources or targets of edges, all such edges SHALL have their endpoints rerouted to connect to the collapsed container node instead of the hidden child resource nodes. The set of logical relationships represented SHALL remain unchanged.

**Validates: Requirements 8.9**

### Property 15: External Resource Sub-Grouping

*For any* set of external resources, each SHALL be assigned to exactly one sub-group: "Cross-Account AWS" (ARN contains different account ID), "On-Premises" (referenced via VPN gateway relationship), "Third-Party" (non-AWS hostname), or "Unknown External" (none of the above). No external resource shall be unassigned.

**Validates: Requirements 9.2**

### Property 16: Viewport Culling Node Bound

*For any* diagram with viewport culling enabled, the number of DOM-rendered nodes SHALL be at most the number of nodes visible in the current viewport plus a 50-node buffer.

**Validates: Requirements 10.3**

## Error Handling

### Backend Errors

| Scenario | Behavior |
|---|---|
| Resource references unknown VPC/subnet | `HierarchyBuilder` creates placeholder container labeled "Unknown VPC" or "Unknown Subnet" |
| No resources found in scan | Return `DiagramData` with empty nodes/edges and `hierarchy` containing only the cloud + account containers |
| Icon file not found on disk | `/api/images/icons/` returns 404; frontend falls back to placeholder icon |
| Hierarchy build fails (unexpected data) | Log error, return `DiagramData` with `hierarchy: null`; frontend falls back to flat dagre layout |

### Frontend Errors

| Scenario | Behavior |
|---|---|
| `hierarchy` field is null in API response | Fall back to existing dagre-based flat layout (backward compatibility) |
| SVG icon fails to load | Render generic placeholder icon (gray square with "?" symbol) |
| Layout computation exceeds 5s | Show progress indicator with cancel button; on cancel, restore previous diagram or show empty canvas |
| Container has circular parent reference | Detect cycle during layout, log warning, render affected containers at region level |
| Edge source/target node not found | Skip that edge silently, log a warning |

### Graceful Degradation Strategy

The feature is designed for progressive enhancement:
1. If `hierarchy` is present → render hierarchical architecture diagram
2. If `hierarchy` is null → fall back to existing dagre flat layout
3. If layout times out → offer cancel and show last good state
4. If icons fail → placeholder icons maintain readability

## Testing Strategy

### Property-Based Tests (Hypothesis + fast-check)

Property-based testing is highly applicable to this feature because:
- The hierarchy builder is a pure transformation (flat resources → tree)
- Layout algorithms have universal geometric invariants (no overlap, minimum spacing)
- Resource placement follows deterministic priority rules across all possible inputs
- Edge styling is a pure mapping function

**Backend (Hypothesis)**:
- Properties 1, 2, 3, 12, 15 — test `HierarchyBuilder` logic
- Minimum 100 iterations per property
- Tag format: `# Feature: architecture-diagram-visualization, Property N: <title>`

**Frontend (fast-check)**:
- Properties 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16 — test layout engine and rendering logic
- Minimum 100 iterations per property
- Tag format: `// Feature: architecture-diagram-visualization, Property N: <title>`

### Unit Tests (Example-Based)

**Backend**:
- Icon resolver mapping for each supported resource type
- API endpoint response shape validation
- Placeholder container creation for unknown VPCs/subnets

**Frontend**:
- ContainerNode renders correct styles for each container type (7.1–7.8)
- BoundaryServiceNode renders at correct position
- Double-click toggles collapse/expand state
- Single-click emits selection event
- Hover highlights connected edges
- Fit view button presence and functionality
- External node styling (50% opacity, dashed border)
- Auto-collapse behavior for >50 containers

### Integration Tests

- End-to-end: scan → hierarchy build → API response → rendered diagram
- Performance: 500 resources + 100 containers layout within 3 seconds
- Edge routing around containers (visual regression)
- Cross-boundary edge rendering for external resources
- Layout timeout and cancel behavior

### Test File Locations

| Test | Location |
|---|---|
| HierarchyBuilder properties | `backend/tests/test_hierarchy_builder_properties.py` |
| HierarchyBuilder unit tests | `backend/tests/test_hierarchy_builder.py` |
| Icon resolver unit tests | `backend/tests/test_icon_resolver.py` |
| Layout engine properties | `frontend/src/layout/HierarchyLayoutEngine.property.test.ts` |
| ContainerNode unit tests | `frontend/src/components/ContainerNode.test.tsx` |
| BoundaryServiceNode tests | `frontend/src/components/BoundaryServiceNode.test.tsx` |
| DiagramCanvas integration | `frontend/src/components/DiagramCanvas.test.tsx` (updated) |
| Edge styling properties | `frontend/src/components/RelationshipEdge.property.test.ts` (updated) |
