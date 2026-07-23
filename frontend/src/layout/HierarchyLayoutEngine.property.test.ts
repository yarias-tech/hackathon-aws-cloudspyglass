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
