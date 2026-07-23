# Implementation Plan: Architecture Diagram Visualization

## Overview

This plan implements the hierarchical AWS architecture diagram visualization feature. Work is organized backend-first (data models, hierarchy builder, icon resolver, API extension) followed by frontend (types, layout engine, container/boundary nodes, edge styling, interactive behaviors, performance optimizations). Each task builds incrementally on prior work, with property-based and unit tests validating correctness at each stage.

## Tasks

- [x] 1. Backend data models and icon resolver
  - [x] 1.1 Create hierarchy Pydantic models (`backend/models/hierarchy.py`)
    - Define `ContainerMetadata`, `BoundaryServicePlacement`, and `HierarchyTree` models
    - Include all fields: id, name, type, parent_id, subnet_type, icon_key, resources, children
    - Add `Literal` type constraints for container types, boundary types, edge positions
    - _Requirements: 6.6_

  - [x] 1.2 Update DiagramData model (`backend/models/diagram.py`)
    - Add optional `hierarchy: HierarchyTree | None = None` field to `DiagramData`
    - Ensure backward compatibility (field defaults to None)
    - _Requirements: 6.5_

  - [x] 1.3 Implement ArchitectureIconResolver (`backend/services/icon_resolver.py`)
    - Map resource types to 48px SVG paths from `Architecture-Service-Icons_07312025`
    - Map container types to 32px SVG paths from `Architecture-Group-Icons_07312025`
    - Support all container types: cloud, account, region, vpc, public subnet, private subnet, az
    - Return placeholder path when no mapping exists
    - _Requirements: 2.1, 2.4_

  - [x] 1.4 Write unit tests for ArchitectureIconResolver (`backend/tests/test_icon_resolver.py`)
    - Test each supported resource type maps to correct SVG path
    - Test each container type maps to correct group icon path
    - Test unknown resource type returns placeholder path
    - _Requirements: 2.1, 2.4, 2.3_

- [x] 2. Backend HierarchyBuilder service
  - [x] 2.1 Implement HierarchyBuilder core (`backend/services/hierarchy_builder.py`)
    - Implement `build()` method: construct tree cloud → account → region → vpc → az → subnet
    - Implement `_classify_subnet_type()`: check route tables for IGW route to determine public/private
    - Implement `_assign_resource_to_container()`: priority-based placement (external → global → subnet → az → vpc → region)
    - Create placeholder containers for unknown VPCs/subnets referenced by resources
    - Assign global services (IAM, Route53, CloudFront, S3, WAF) to account-level container
    - Detect and populate boundary service placements (IGW, NAT, WAF, VPN)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.7, 5.1, 5.2, 5.3, 5.4_

  - [x] 2.2 Write property test: Hierarchy Nesting Order (`backend/tests/test_hierarchy_builder_properties.py`)
    - **Property 1: Hierarchy Nesting Order**
    - Generate random scan data with resources across accounts, regions, VPCs, AZs, subnets
    - Assert every container's parent type follows strict ordering: cloud → account → region → vpc → az → subnet
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6, 6.1**

  - [x] 2.3 Write property test: Subnet Classification Correctness (`backend/tests/test_hierarchy_builder_properties.py`)
    - **Property 2: Subnet Classification Correctness**
    - Generate subnets with varying route table configurations
    - Assert public classification iff route table has 0.0.0.0/0 → IGW; private otherwise
    - **Validates: Requirements 1.7, 1.8, 6.3**

  - [x] 2.4 Write property test: Resource Placement Priority (`backend/tests/test_hierarchy_builder_properties.py`)
    - **Property 3: Resource Placement Priority**
    - Generate resources with various combinations of is_external, global type, subnet_id, vpc_id, az
    - Assert each resource is assigned to exactly one container per priority rules
    - Assert no resource is unassigned and no resource appears in multiple containers
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.2, 6.7**

  - [x] 2.5 Write property test: Container Metadata Completeness (`backend/tests/test_hierarchy_builder_properties.py`)
    - **Property 12: Container Metadata Completeness**
    - Generate scan data and build hierarchy
    - Assert every container has non-empty id, non-empty name, valid type, icon_key, and resources array
    - Assert parent_id is null only for root container
    - **Validates: Requirements 6.6**

  - [x] 2.6 Write property test: External Resource Sub-Grouping (`backend/tests/test_hierarchy_builder_properties.py`)
    - **Property 15: External Resource Sub-Grouping**
    - Generate external resources with different characteristics (cross-account ARN, VPN ref, non-AWS hostname)
    - Assert each external resource is assigned to exactly one sub-group category
    - **Validates: Requirements 9.2**

  - [x] 2.7 Write unit tests for HierarchyBuilder (`backend/tests/test_hierarchy_builder.py`)
    - Test tree construction with a typical multi-VPC, multi-AZ scan
    - Test placeholder container creation for unknown VPC
    - Test default private classification when no route table exists
    - Test empty scan returns minimal hierarchy (cloud + account containers only)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 3. Backend API integration
  - [x] 3.1 Update diagrams route to include hierarchy (`backend/routes/diagrams.py`)
    - Integrate HierarchyBuilder into the `/api/diagrams/latest` endpoint
    - Call `HierarchyBuilder.build()` after relationship resolution
    - Attach resulting `HierarchyTree` to `DiagramData.hierarchy`
    - Handle build failure gracefully: set `hierarchy = None` and log error
    - _Requirements: 6.5_

  - [x] 3.2 Write integration test for diagrams endpoint (`backend/tests/test_diagrams_route.py`)
    - Test that `/api/diagrams/latest` response includes `hierarchy` field
    - Test that hierarchy is null when no scan data exists
    - Test backward compatibility: existing fields unchanged
    - _Requirements: 6.5_

- [x] 4. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Frontend types and layout engine
  - [ ] 5.1 Create hierarchy TypeScript types (`frontend/src/types/hierarchy.ts`)
    - Define `ContainerType`, `SubnetType`, `BoundaryType`, `EdgePosition` type aliases
    - Define `ContainerMetadata`, `BoundaryServicePlacement`, `HierarchyTree` interfaces
    - _Requirements: 6.6_

  - [ ] 5.2 Update DiagramData type (`frontend/src/types/diagram.ts`)
    - Add `hierarchy: HierarchyTree | null` field to `DiagramData` interface
    - Import `HierarchyTree` from `./hierarchy`
    - _Requirements: 6.5_

  - [ ] 5.3 Implement HierarchyLayoutEngine (`frontend/src/layout/HierarchyLayoutEngine.ts`)
    - Implement `computeHierarchyLayout()` function
    - Recursive container sizing: parent sizes based on children + padding (20px min)
    - Grid/flow sub-layout for resource nodes within containers (16px spacing)
    - Enforce minimum container dimensions (100x60px for empty containers)
    - Position boundary services on container edges (50% inside, 50% outside)
    - Space multiple boundary services on same edge with 20px gap
    - Position external resources area to the right of AWS Cloud container (40px gap)
    - _Requirements: 1.9, 1.10, 1.11, 3.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 9.1_

  - [ ]* 5.4 Write property test: No Sibling Overlap (`frontend/src/layout/HierarchyLayoutEngine.property.test.ts`)
    - **Property 4: No Sibling Overlap in Layout**
    - Generate hierarchies with varying container and resource counts
    - Assert no two sibling nodes have overlapping bounding boxes
    - **Validates: Requirements 1.9, 3.8**

  - [ ]* 5.5 Write property test: Minimum Parent Padding (`frontend/src/layout/HierarchyLayoutEngine.property.test.ts`)
    - **Property 5: Minimum Parent Padding**
    - Generate containers with children
    - Assert every child's bounding box is at least 20px from parent border on all sides
    - **Validates: Requirements 1.10**

  - [ ]* 5.6 Write property test: Minimum Container Dimensions (`frontend/src/layout/HierarchyLayoutEngine.property.test.ts`)
    - **Property 6: Minimum Container Dimensions**
    - Generate empty containers (no resources, no sub-containers)
    - Assert width ≥ 100px and height ≥ 60px
    - **Validates: Requirements 1.11**

  - [ ]* 5.7 Write property test: Boundary Service Positioning (`frontend/src/layout/HierarchyLayoutEngine.property.test.ts`)
    - **Property 10: Boundary Service Positioning**
    - Generate boundary services with designated container edges
    - Assert node center lies on the container border line
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [ ]* 5.8 Write property test: Boundary Service Spacing (`frontend/src/layout/HierarchyLayoutEngine.property.test.ts`)
    - **Property 11: Boundary Service Spacing**
    - Generate multiple boundary services on same container edge
    - Assert horizontal distance between adjacent nodes ≥ 20px
    - **Validates: Requirements 5.7**

- [ ] 6. Frontend container and node components
  - [ ] 6.1 Implement ContainerNode component (`frontend/src/components/ContainerNode.tsx`)
    - Render styled container with header bar (icon badge 32x32 + label 14px/600 weight)
    - Apply styling per container type (colors, borders, backgrounds from design spec)
    - Support collapsed state: show only label + resource count badge
    - Handle double-click to toggle collapse/expand
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.3, 8.4_

  - [ ] 6.2 Implement BoundaryServiceNode component (`frontend/src/components/BoundaryServiceNode.tsx`)
    - Render resource icon (48x48) with label
    - Visual styling to indicate boundary positioning
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 6.3 Implement ExternalResourcesContainer (`frontend/src/components/ExternalResourcesContainer.tsx`)
    - Render dedicated external resources area
    - Sub-group by category: Cross-Account AWS, On-Premises, Third-Party, Unknown External
    - Style external nodes with 50% opacity and dashed border
    - _Requirements: 9.1, 9.2, 9.4, 9.5_

  - [ ]* 6.4 Write unit tests for ContainerNode (`frontend/src/components/ContainerNode.test.tsx`)
    - Test correct styles for each container type (7 types)
    - Test collapsed state shows resource count badge
    - Test double-click toggles expand/collapse
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.3, 8.4_

  - [ ]* 6.5 Write unit tests for BoundaryServiceNode (`frontend/src/components/BoundaryServiceNode.test.tsx`)
    - Test renders icon and label correctly
    - Test each boundary type renders appropriately
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 6.6 Write property test: Collapsed Container Badge Count (`frontend/src/components/ContainerNode.property.test.ts`)
    - **Property 13: Collapsed Container Badge Count**
    - Generate containers with nested sub-containers and resources
    - Assert badge count equals total recursive resource count
    - **Validates: Requirements 8.4**

- [ ] 7. Checkpoint - Components complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Edge rendering and resource node updates
  - [ ] 8.1 Update edge rendering with category-based styling (`frontend/src/components/RelationshipEdge.tsx`)
    - Apply color and line style based on relationship category (network→blue/solid, iam→red/dashed, event→orange/dotted, data→purple/solid, other→gray/solid)
    - Implement label truncation (40 chars + ellipsis)
    - Implement hover behavior: increase stroke to 3px, show tooltip with derived_from or category+names
    - Route edges around container boundaries
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 9.3_

  - [ ] 8.2 Update ResourceNode rendering (`frontend/src/components/ResourceNode.tsx`)
    - Render AWS icon at 48x48 centered above resource name label
    - Fall back to generic placeholder icon (gray square with "?") on load failure
    - _Requirements: 2.2, 2.3, 2.6_

  - [ ]* 8.3 Write property test: Edge Category-to-Style Mapping (`frontend/src/components/RelationshipEdge.property.test.ts`)
    - **Property 7: Edge Category-to-Style Mapping**
    - Generate edges with all category values (network, iam, event, data, unknown)
    - Assert rendered style matches category deterministically
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.9**

  - [ ]* 8.4 Write property test: Edge Label Truncation (`frontend/src/components/RelationshipEdge.property.test.ts`)
    - **Property 8: Edge Label Truncation**
    - Generate edge labels of varying lengths (0 to 200 chars)
    - Assert labels >40 chars display first 40 + "…"; labels ≤40 chars display unmodified
    - **Validates: Requirements 4.6**

  - [ ]* 8.5 Write property test: Edge Count Matches Relationships (`frontend/src/components/RelationshipEdge.property.test.ts`)
    - **Property 9: Edge Count Matches Relationships**
    - Generate relationship sets of varying sizes
    - Assert rendered edge count equals relationship count with matching source/target
    - **Validates: Requirements 4.1**

- [ ] 9. DiagramCanvas integration and interactive behaviors
  - [ ] 9.1 Update DiagramCanvas to use hierarchical layout (`frontend/src/components/DiagramCanvas.tsx`)
    - Replace `applyDagreLayout` with `computeHierarchyLayout`
    - Register `ContainerNode`, `BoundaryServiceNode` as custom node types
    - Manage collapsed container state via `useState<Set<string>>`
    - Fall back to dagre layout when `hierarchy` is null (backward compat)
    - _Requirements: 1.1, 6.5_

  - [ ] 9.2 Implement interactive behaviors in DiagramCanvas
    - Pan and zoom with range 0.1x to 5.0x
    - Fit view on initial load (all nodes visible in viewport)
    - "Fit view" button to reset viewport
    - Single-click resource node: emit selection event with ARN
    - Hover resource node: highlight connected edges (3px stroke), dim unrelated edges (20% opacity)
    - Mouse leave: restore all edges to default
    - Reroute edges to collapsed container node when children are hidden
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [ ]* 9.3 Write property test: Edge Rerouting on Collapse (`frontend/src/components/DiagramCanvas.property.test.ts`)
    - **Property 14: Edge Rerouting on Collapse**
    - Generate containers with resources that are edge sources/targets, then collapse
    - Assert edges reroute to container node; total logical relationship count unchanged
    - **Validates: Requirements 8.9**

  - [ ]* 9.4 Write unit tests for DiagramCanvas interactive behaviors (`frontend/src/components/DiagramCanvas.test.tsx`)
    - Test fit view on load
    - Test hover highlight/dim behavior
    - Test click emits selection event
    - Test collapse/expand toggle via double-click
    - Test fallback to dagre when hierarchy is null
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8_

- [ ] 10. Performance optimizations
  - [ ] 10.1 Implement viewport culling (`frontend/src/components/DiagramCanvas.tsx`)
    - Enable viewport culling when resource count exceeds 200
    - Render only visible nodes + 50-node buffer
    - Auto-collapse containers deeper than 2 levels when >50 containers present
    - _Requirements: 10.2, 10.3, 10.4_

  - [ ] 10.2 Implement layout timeout with progress indicator
    - Show progress indicator if layout exceeds 5 seconds
    - Provide cancel button to stop computation
    - On cancel: restore last rendered state or show empty canvas
    - _Requirements: 10.5_

  - [ ]* 10.3 Write property test: Viewport Culling Node Bound (`frontend/src/components/DiagramCanvas.property.test.ts`)
    - **Property 16: Viewport Culling Node Bound**
    - Generate diagrams with >200 resources and a defined viewport
    - Assert DOM-rendered node count ≤ visible nodes + 50 buffer
    - **Validates: Requirements 10.3**

- [ ] 11. Final checkpoint - All features integrated
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (16 total)
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.12+ with Hypothesis for property-based tests
- Frontend uses TypeScript with fast-check for property-based tests
- The feature gracefully degrades: when `hierarchy` is null, the existing dagre layout is used

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "5.1"] },
    { "id": 1, "tasks": ["1.2", "1.4", "5.2"] },
    { "id": 2, "tasks": ["2.1", "5.3"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "5.4", "5.5", "5.6", "5.7", "5.8"] },
    { "id": 4, "tasks": ["3.1", "6.1", "6.2", "6.3"] },
    { "id": 5, "tasks": ["3.2", "6.4", "6.5", "6.6"] },
    { "id": 6, "tasks": ["8.1", "8.2"] },
    { "id": 7, "tasks": ["8.3", "8.4", "8.5"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2"] },
    { "id": 10, "tasks": ["9.3", "9.4"] },
    { "id": 11, "tasks": ["10.1", "10.2"] },
    { "id": 12, "tasks": ["10.3"] }
  ]
}
```
