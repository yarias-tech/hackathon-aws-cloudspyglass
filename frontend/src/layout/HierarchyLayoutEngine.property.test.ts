// Feature: architecture-diagram-visualization, Property 4: No Sibling Overlap in Layout
import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { computeHierarchyLayout } from './HierarchyLayoutEngine';
import type { HierarchyTree, ContainerMetadata, ContainerType } from '../types/hierarchy';
import type { DiagramNode, DiagramEdge } from '../types/diagram';

/**
 * **Validates: Requirements 1.9, 3.8**
 *
 * Property 4: No Sibling Overlap in Layout
 * For any layout result, no two sibling nodes (resource nodes or sub-containers
 * sharing the same parent container) SHALL have overlapping bounding boxes.
 */

// ─── Constants matching the layout engine ─────────────────────────────────────
const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

// ─── Container type nesting order ─────────────────────────────────────────────
const CONTAINER_TYPE_DEPTH: Record<ContainerType, number> = {
  cloud: 0,
  account: 1,
  region: 2,
  vpc: 3,
  az: 4,
  subnet: 5,
};

const CONTAINER_TYPES_ORDERED: ContainerType[] = ['cloud', 'account', 'region', 'vpc', 'az', 'subnet'];

// ─── Arbitrary: Valid Hierarchy Tree with DiagramNodes ─────────────────────────

interface GeneratedHierarchy {
  hierarchy: HierarchyTree;
  diagramNodes: DiagramNode[];
  diagramEdges: DiagramEdge[];
}

/**
 * Generates a valid HierarchyTree with properly nested containers and resources.
 * Ensures:
 * - Single root of type 'cloud'
 * - Proper parent-child references
 * - Container types follow nesting order
 * - Resources are assigned to leaf-ish containers
 */
const hierarchyArb: fc.Arbitrary<GeneratedHierarchy> = fc
  .record({
    numContainersPerLevel: fc.array(fc.integer({ min: 1, max: 3 }), { minLength: 1, maxLength: 5 }),
    resourcesPerContainer: fc.integer({ min: 0, max: 5 }),
  })
  .chain(({ numContainersPerLevel, resourcesPerContainer }) => {
    return fc.constant(null).map(() => {
      const containers: ContainerMetadata[] = [];
      const diagramNodes: DiagramNode[] = [];
      let containerIdCounter = 0;
      let resourceIdCounter = 0;

      // Create root (cloud)
      const rootId = `container-${containerIdCounter++}`;
      const rootContainer: ContainerMetadata = {
        id: rootId,
        name: 'AWS Cloud',
        type: 'cloud',
        parent_id: null,
        subnet_type: null,
        icon_key: 'aws-cloud',
        resources: [],
        children: [],
      };
      containers.push(rootContainer);

      // Build hierarchy level by level
      let currentLevelParents = [rootContainer];

      // Determine how many levels to create (up to numContainersPerLevel length, max depth 5 for subnet)
      const maxDepth = Math.min(numContainersPerLevel.length, CONTAINER_TYPES_ORDERED.length - 1);

      for (let depth = 1; depth <= maxDepth; depth++) {
        const containerType = CONTAINER_TYPES_ORDERED[depth];
        const numContainersAtLevel = numContainersPerLevel[depth - 1];
        const nextLevelParents: ContainerMetadata[] = [];

        for (const parent of currentLevelParents) {
          for (let i = 0; i < numContainersAtLevel; i++) {
            const containerId = `container-${containerIdCounter++}`;
            const container: ContainerMetadata = {
              id: containerId,
              name: `${containerType}-${containerId}`,
              type: containerType,
              parent_id: parent.id,
              subnet_type: containerType === 'subnet' ? (i % 2 === 0 ? 'public' : 'private') : null,
              icon_key: `icon-${containerType}`,
              resources: [],
              children: [],
            };
            containers.push(container);
            parent.children.push(containerId);
            nextLevelParents.push(container);
          }
        }

        currentLevelParents = nextLevelParents;
      }

      // Add resources to leaf containers (and some to intermediate ones)
      const leafContainers = containers.filter(
        (c) => c.children.length === 0 && c.type !== 'cloud'
      );

      // If no leaf containers besides root, use all non-root containers
      const targetContainers = leafContainers.length > 0 ? leafContainers : containers.filter(c => c.type !== 'cloud');

      for (const container of targetContainers) {
        const numResources = Math.min(resourcesPerContainer, 5);
        for (let i = 0; i < numResources; i++) {
          const resourceId = `resource-${resourceIdCounter++}`;
          container.resources.push(resourceId);

          diagramNodes.push({
            id: resourceId,
            resource_type: 'aws::ec2::instance',
            name: `Resource ${resourceId}`,
            region: 'us-east-1',
            is_external: false,
            is_unresolved: false,
            icon_url: '/icons/ec2.svg',
          });
        }
      }

      const hierarchy: HierarchyTree = {
        containers,
        root_id: rootId,
        boundary_services: [],
      };

      return {
        hierarchy,
        diagramNodes,
        diagramEdges: [] as DiagramEdge[],
      };
    });
  });

// ─── Overlap Detection Helper ─────────────────────────────────────────────────

interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Returns true if two bounding boxes overlap (strict overlap, not touching).
 */
function boxesOverlap(a: BoundingBox, b: BoundingBox): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

/**
 * Gets the bounding box for a node in the layout result.
 * - Container nodes use style.width and style.height
 * - Resource nodes use fixed NODE_WIDTH x NODE_HEIGHT
 */
function getNodeBoundingBox(node: { position: { x: number; y: number }; style?: Record<string, unknown>; type?: string }): BoundingBox {
  let width: number;
  let height: number;

  if (node.type === 'container' && node.style) {
    width = typeof node.style.width === 'number' ? node.style.width : NODE_WIDTH;
    height = typeof node.style.height === 'number' ? node.style.height : NODE_HEIGHT;
  } else {
    width = NODE_WIDTH;
    height = NODE_HEIGHT;
  }

  return {
    x: node.position.x,
    y: node.position.y,
    width,
    height,
  };
}

// ─── Property Test ────────────────────────────────────────────────────────────

describe('Property 4: No Sibling Overlap in Layout', () => {
  it('no two sibling nodes have overlapping bounding boxes', () => {
    fc.assert(
      fc.property(hierarchyArb, ({ hierarchy, diagramNodes, diagramEdges }) => {
        const result = computeHierarchyLayout(hierarchy, diagramNodes, diagramEdges);

        // Group nodes by their parentId (siblings share the same parentId)
        const siblingGroups = new Map<string, typeof result.nodes>();

        for (const node of result.nodes) {
          // parentId can be undefined (top-level) or a string
          const parentKey = (node as { parentId?: string }).parentId ?? '__root__';
          const group = siblingGroups.get(parentKey) || [];
          group.push(node);
          siblingGroups.set(parentKey, group);
        }

        // Check each sibling group for overlaps
        for (const [, siblings] of siblingGroups) {
          for (let i = 0; i < siblings.length; i++) {
            for (let j = i + 1; j < siblings.length; j++) {
              const boxA = getNodeBoundingBox(siblings[i] as { position: { x: number; y: number }; style?: Record<string, unknown>; type?: string });
              const boxB = getNodeBoundingBox(siblings[j] as { position: { x: number; y: number }; style?: Record<string, unknown>; type?: string });

              expect(
                boxesOverlap(boxA, boxB),
                `Sibling nodes "${siblings[i].id}" and "${siblings[j].id}" overlap.\n` +
                `  Node A: (${boxA.x}, ${boxA.y}) ${boxA.width}x${boxA.height}\n` +
                `  Node B: (${boxB.x}, ${boxB.y}) ${boxB.width}x${boxB.height}`
              ).toBe(false);
            }
          }
        }
      }),
      { numRuns: 100 }
    );
  });
});

// Feature: architecture-diagram-visualization, Property 5: Minimum Parent Padding

/**
 * **Validates: Requirements 1.10**
 *
 * Property 5: Minimum Parent Padding
 * For any container in the layout result that has children, every child node's
 * bounding box SHALL be at least 20 pixels from the parent container's border
 * on all sides.
 */
describe('Property 5: Minimum Parent Padding', () => {
  it('every child node is at least 20px from parent border on all sides', () => {
    fc.assert(
      fc.property(hierarchyArb, ({ hierarchy, diagramNodes, diagramEdges }) => {
        const result = computeHierarchyLayout(hierarchy, diagramNodes, diagramEdges);

        const MIN_PADDING = 20;

        // Build a map of node id -> node for quick lookup
        const nodeMap = new Map<string, (typeof result.nodes)[number]>();
        for (const node of result.nodes) {
          nodeMap.set(node.id, node);
        }

        // Check every node that has a parentId
        for (const node of result.nodes) {
          const parentId = (node as { parentId?: string }).parentId;
          if (!parentId) continue;

          const parent = nodeMap.get(parentId);
          if (!parent) continue;

          // Get child bounding box (position is relative to parent)
          const childBox = getNodeBoundingBox(
            node as { position: { x: number; y: number }; style?: Record<string, unknown>; type?: string }
          );

          // Get parent dimensions from style
          const parentStyle = (parent as { style?: Record<string, unknown> }).style;
          const parentWidth = typeof parentStyle?.width === 'number' ? parentStyle.width : 0;
          const parentHeight = typeof parentStyle?.height === 'number' ? parentStyle.height : 0;

          // Positions are relative to the parent, so parent origin is (0, 0)
          // Left padding: child.x >= 20
          expect(
            childBox.x,
            `Node "${node.id}" left padding from parent "${parentId}" is less than ${MIN_PADDING}px. ` +
            `child.x=${childBox.x}`
          ).toBeGreaterThanOrEqual(MIN_PADDING);

          // Top padding: child.y >= 20
          expect(
            childBox.y,
            `Node "${node.id}" top padding from parent "${parentId}" is less than ${MIN_PADDING}px. ` +
            `child.y=${childBox.y}`
          ).toBeGreaterThanOrEqual(MIN_PADDING);

          // Right padding: child.x + child.width <= parentWidth - 20
          expect(
            childBox.x + childBox.width,
            `Node "${node.id}" right padding from parent "${parentId}" is less than ${MIN_PADDING}px. ` +
            `child.x + child.width=${childBox.x + childBox.width}, parentWidth - 20=${parentWidth - MIN_PADDING}`
          ).toBeLessThanOrEqual(parentWidth - MIN_PADDING);

          // Bottom padding: child.y + child.height <= parentHeight - 20
          expect(
            childBox.y + childBox.height,
            `Node "${node.id}" bottom padding from parent "${parentId}" is less than ${MIN_PADDING}px. ` +
            `child.y + child.height=${childBox.y + childBox.height}, parentHeight - 20=${parentHeight - MIN_PADDING}`
          ).toBeLessThanOrEqual(parentHeight - MIN_PADDING);
        }
      }),
      { numRuns: 100 }
    );
  });
});

// Feature: architecture-diagram-visualization, Property 6: Minimum Container Dimensions

/**
 * **Validates: Requirements 1.11**
 *
 * Property 6: Minimum Container Dimensions
 * For any container in the layout result that has no children (no resources and
 * no sub-containers), its rendered width SHALL be at least 100 pixels and its
 * rendered height SHALL be at least 60 pixels.
 */

// ─── Arbitrary: Hierarchy with empty containers ───────────────────────────────

/**
 * Generates a HierarchyTree that always includes at least one empty container
 * (no resources, no sub-containers). The root cloud container has children, but
 * the leaf containers are left completely empty.
 */
const emptyContainerHierarchyArb: fc.Arbitrary<GeneratedHierarchy> = fc
  .record({
    numEmptyContainers: fc.integer({ min: 1, max: 4 }),
    depth: fc.integer({ min: 1, max: 4 }),
  })
  .map(({ numEmptyContainers, depth }) => {
    const containers: ContainerMetadata[] = [];
    let containerIdCounter = 0;

    // Create root (cloud)
    const rootId = `container-${containerIdCounter++}`;
    const rootContainer: ContainerMetadata = {
      id: rootId,
      name: 'AWS Cloud',
      type: 'cloud',
      parent_id: null,
      subnet_type: null,
      icon_key: 'aws-cloud',
      resources: [],
      children: [],
    };
    containers.push(rootContainer);

    // Build a path of containers down to the target depth
    let currentParent = rootContainer;
    for (let d = 1; d < depth; d++) {
      const containerType = CONTAINER_TYPES_ORDERED[d];
      const containerId = `container-${containerIdCounter++}`;
      const container: ContainerMetadata = {
        id: containerId,
        name: `${containerType}-${containerId}`,
        type: containerType,
        parent_id: currentParent.id,
        subnet_type: containerType === 'subnet' ? 'public' : null,
        icon_key: `icon-${containerType}`,
        resources: [],
        children: [],
      };
      containers.push(container);
      currentParent.children.push(containerId);
      currentParent = container;
    }

    // Add empty leaf containers (no resources, no children) to the current parent
    const leafType = CONTAINER_TYPES_ORDERED[Math.min(depth, CONTAINER_TYPES_ORDERED.length - 1)];
    for (let i = 0; i < numEmptyContainers; i++) {
      const containerId = `container-${containerIdCounter++}`;
      const container: ContainerMetadata = {
        id: containerId,
        name: `empty-${leafType}-${containerId}`,
        type: leafType,
        parent_id: currentParent.id,
        subnet_type: leafType === 'subnet' ? (i % 2 === 0 ? 'public' : 'private') : null,
        icon_key: `icon-${leafType}`,
        resources: [],       // No resources
        children: [],        // No sub-containers
      };
      containers.push(container);
      currentParent.children.push(containerId);
    }

    const hierarchy: HierarchyTree = {
      containers,
      root_id: rootId,
      boundary_services: [],
    };

    return {
      hierarchy,
      diagramNodes: [] as DiagramNode[],
      diagramEdges: [] as DiagramEdge[],
    };
  });

// ─── Property Test ────────────────────────────────────────────────────────────

describe('Property 6: Minimum Container Dimensions', () => {
  it('empty containers (no resources, no sub-containers) have width >= 100px and height >= 60px', () => {
    const MIN_CONTAINER_WIDTH = 100;
    const MIN_CONTAINER_HEIGHT = 60;

    fc.assert(
      fc.property(emptyContainerHierarchyArb, ({ hierarchy, diagramNodes, diagramEdges }) => {
        const result = computeHierarchyLayout(hierarchy, diagramNodes, diagramEdges);

        // Identify empty containers from the hierarchy input
        const emptyContainerIds = new Set(
          hierarchy.containers
            .filter((c) => c.resources.length === 0 && c.children.length === 0)
            .map((c) => c.id)
        );

        // Check every container node in the result that corresponds to an empty container
        for (const node of result.nodes) {
          if (node.type !== 'container') continue;
          if (!emptyContainerIds.has(node.id)) continue;

          const style = (node as { style?: Record<string, unknown> }).style;
          const width = typeof style?.width === 'number' ? style.width : 0;
          const height = typeof style?.height === 'number' ? style.height : 0;

          expect(
            width,
            `Empty container "${node.id}" has width ${width}px, expected >= ${MIN_CONTAINER_WIDTH}px`
          ).toBeGreaterThanOrEqual(MIN_CONTAINER_WIDTH);

          expect(
            height,
            `Empty container "${node.id}" has height ${height}px, expected >= ${MIN_CONTAINER_HEIGHT}px`
          ).toBeGreaterThanOrEqual(MIN_CONTAINER_HEIGHT);
        }
      }),
      { numRuns: 100 }
    );
  });
});

// Feature: architecture-diagram-visualization, Property 10: Boundary Service Positioning

/**
 * **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
 *
 * Property 10: Boundary Service Positioning
 * For any boundary service (internet_gateway, nat_gateway, waf, vpn_gateway) in
 * the layout, the node's center coordinates SHALL lie on the border line of its
 * designated container edge, resulting in approximately 50% of the node area
 * inside and 50% outside the container boundary.
 */

// ─── Constants matching the layout engine for boundary nodes ──────────────────
const BOUNDARY_NODE_WIDTH = 120;
const BOUNDARY_NODE_HEIGHT = 60;

// ─── Arbitrary: Hierarchy with Boundary Services ──────────────────────────────

type BoundaryTypeValue = 'igw' | 'nat' | 'waf' | 'vpn';
type EdgePositionValue = 'top' | 'bottom' | 'left' | 'right';

interface BoundaryTestHierarchy {
  hierarchy: HierarchyTree;
  diagramNodes: DiagramNode[];
  diagramEdges: DiagramEdge[];
  expectedBoundary: {
    resourceArn: string;
    innerContainerId: string;
    edgePosition: EdgePositionValue;
  }[];
}

/**
 * Generates a valid HierarchyTree with a cloud → account → region → vpc chain
 * and 1-3 boundary services attached to the VPC container with various edge positions.
 */
const boundaryServiceHierarchyArb: fc.Arbitrary<BoundaryTestHierarchy> = fc
  .record({
    numBoundaryServices: fc.integer({ min: 1, max: 3 }),
    boundaryTypes: fc.array(
      fc.constantFrom<BoundaryTypeValue>('igw', 'nat', 'waf', 'vpn'),
      { minLength: 3, maxLength: 3 }
    ),
    edgePositions: fc.array(
      fc.constantFrom<EdgePositionValue>('top', 'bottom', 'left', 'right'),
      { minLength: 3, maxLength: 3 }
    ),
    numResources: fc.integer({ min: 1, max: 3 }),
  })
  .map(({ numBoundaryServices, boundaryTypes, edgePositions, numResources }) => {
    const containers: ContainerMetadata[] = [];
    const diagramNodes: DiagramNode[] = [];

    // Build cloud → account → region → vpc hierarchy
    const cloudId = 'cloud-root';
    const accountId = 'account-1';
    const regionId = 'region-us-east-1';
    const vpcId = 'vpc-abc123';

    containers.push({
      id: cloudId,
      name: 'AWS Cloud',
      type: 'cloud',
      parent_id: null,
      subnet_type: null,
      icon_key: 'aws-cloud',
      resources: [],
      children: [accountId],
    });

    containers.push({
      id: accountId,
      name: 'Account 123456789012',
      type: 'account',
      parent_id: cloudId,
      subnet_type: null,
      icon_key: 'aws-account',
      resources: [],
      children: [regionId],
    });

    containers.push({
      id: regionId,
      name: 'us-east-1',
      type: 'region',
      parent_id: accountId,
      subnet_type: null,
      icon_key: 'region',
      resources: [],
      children: [vpcId],
    });

    // VPC container holds the resources - boundary services attach to it
    const vpcResources: string[] = [];
    for (let i = 0; i < numResources; i++) {
      const resId = `arn:aws:ec2:us-east-1:123456789012:instance/i-${i}`;
      vpcResources.push(resId);
      diagramNodes.push({
        id: resId,
        resource_type: 'aws::ec2::instance',
        name: `Instance ${i}`,
        region: 'us-east-1',
        is_external: false,
        is_unresolved: false,
        icon_url: '/icons/ec2.svg',
      });
    }

    containers.push({
      id: vpcId,
      name: 'VPC abc123',
      type: 'vpc',
      parent_id: regionId,
      subnet_type: null,
      icon_key: 'vpc',
      resources: vpcResources,
      children: [],
    });

    // Create boundary services attached to the VPC
    const boundaryServices: import('../types/hierarchy').BoundaryServicePlacement[] = [];
    const expectedBoundary: BoundaryTestHierarchy['expectedBoundary'] = [];

    // All boundary services on the same edge so they are grouped together
    const chosenEdge = edgePositions[0];

    for (let i = 0; i < numBoundaryServices; i++) {
      const bType = boundaryTypes[i % boundaryTypes.length];
      const resourceArn = `arn:aws:ec2:us-east-1:123456789012:${bType}/bs-${i}`;

      boundaryServices.push({
        resource_arn: resourceArn,
        boundary_type: bType,
        inner_container_id: vpcId,
        outer_container_id: regionId,
        edge_position: chosenEdge,
      });

      diagramNodes.push({
        id: resourceArn,
        resource_type: `aws::ec2::${bType}`,
        name: `${bType}-${i}`,
        region: 'us-east-1',
        is_external: false,
        is_unresolved: false,
        icon_url: `/icons/${bType}.svg`,
      });

      expectedBoundary.push({
        resourceArn,
        innerContainerId: vpcId,
        edgePosition: chosenEdge,
      });
    }

    const hierarchy: HierarchyTree = {
      containers,
      root_id: cloudId,
      boundary_services: boundaryServices,
    };

    return {
      hierarchy,
      diagramNodes,
      diagramEdges: [] as DiagramEdge[],
      expectedBoundary,
    };
  });

// ─── Property Test ────────────────────────────────────────────────────────────

describe('Property 10: Boundary Service Positioning', () => {
  it('boundary service node center lies on the designated container border line', () => {
    fc.assert(
      fc.property(boundaryServiceHierarchyArb, ({ hierarchy, diagramNodes, diagramEdges, expectedBoundary }) => {
        const result = computeHierarchyLayout(hierarchy, diagramNodes, diagramEdges);

        // Build a map of node id -> node for quick lookup
        const nodeMap = new Map<string, (typeof result.nodes)[number]>();
        for (const node of result.nodes) {
          nodeMap.set(node.id, node);
        }

        for (const expected of expectedBoundary) {
          // Find the boundary-type node specifically (the same id may also appear
          // as an external node since boundary resources aren't in container.resources)
          const boundaryNode = result.nodes.find(
            (n) => n.id === expected.resourceArn && n.type === 'boundary'
          );
          expect(
            boundaryNode,
            `Boundary node "${expected.resourceArn}" (type=boundary) should exist in layout result`
          ).toBeDefined();

          if (!boundaryNode) continue;

          // The container node for the inner_container_id
          const containerNode = nodeMap.get(expected.innerContainerId);
          expect(
            containerNode,
            `Container node "${expected.innerContainerId}" should exist in layout result`
          ).toBeDefined();

          if (!containerNode) continue;

          // Get container dimensions from style
          const containerStyle = (containerNode as { style?: Record<string, unknown> }).style;
          const containerWidth = typeof containerStyle?.width === 'number' ? containerStyle.width : 0;
          const containerHeight = typeof containerStyle?.height === 'number' ? containerStyle.height : 0;

          // Boundary node center:
          //   centerX = boundaryNode.position.x + BOUNDARY_NODE_WIDTH / 2
          //   centerY = boundaryNode.position.y + BOUNDARY_NODE_HEIGHT / 2
          //
          // Both boundaryNode.position and containerNode.position are relative to
          // the container's parent (since boundaryNode.parentId = container's parentId).
          const centerX = boundaryNode.position.x + BOUNDARY_NODE_WIDTH / 2;
          const centerY = boundaryNode.position.y + BOUNDARY_NODE_HEIGHT / 2;

          switch (expected.edgePosition) {
            case 'top':
              // Node center Y should equal container's top Y
              expect(
                centerY,
                `Boundary node "${expected.resourceArn}" center Y (${centerY}) should equal ` +
                `container top Y (${containerNode.position.y}) for edge_position="top"`
              ).toBe(containerNode.position.y);
              break;

            case 'bottom':
              // Node center Y should equal container's bottom Y (position.y + height)
              expect(
                centerY,
                `Boundary node "${expected.resourceArn}" center Y (${centerY}) should equal ` +
                `container bottom Y (${containerNode.position.y + containerHeight}) for edge_position="bottom"`
              ).toBe(containerNode.position.y + containerHeight);
              break;

            case 'left':
              // Node center X should equal container's left X
              expect(
                centerX,
                `Boundary node "${expected.resourceArn}" center X (${centerX}) should equal ` +
                `container left X (${containerNode.position.x}) for edge_position="left"`
              ).toBe(containerNode.position.x);
              break;

            case 'right':
              // Node center X should equal container's right X (position.x + width)
              expect(
                centerX,
                `Boundary node "${expected.resourceArn}" center X (${centerX}) should equal ` +
                `container right X (${containerNode.position.x + containerWidth}) for edge_position="right"`
              ).toBe(containerNode.position.x + containerWidth);
              break;
          }
        }
      }),
      { numRuns: 100 }
    );
  });
});
