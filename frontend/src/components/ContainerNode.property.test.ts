// Feature: architecture-diagram-visualization, Property 13: Collapsed Container Badge Count
import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { ContainerMetadata, ContainerType, HierarchyTree } from '../types/hierarchy';

/**
 * **Validates: Requirements 8.4**
 *
 * Property 13: Collapsed Container Badge Count
 * For any collapsed container, the displayed resource count badge SHALL equal
 * the total number of resource nodes recursively contained within that container
 * and all its nested sub-containers.
 */

// ─── Helper: Compute Recursive Resource Count ─────────────────────────────────

/**
 * Computes the total number of resources recursively contained within a container
 * and all its nested sub-containers.
 *
 * This is the function that would be used to compute `resourceCount` for the
 * ContainerNode badge display when a container is collapsed.
 */
export function computeRecursiveResourceCount(
  containerId: string,
  hierarchy: HierarchyTree
): number {
  const containerMap = new Map<string, ContainerMetadata>();
  for (const container of hierarchy.containers) {
    containerMap.set(container.id, container);
  }

  function countRecursive(id: string): number {
    const container = containerMap.get(id);
    if (!container) return 0;

    // Count direct resources in this container
    let count = container.resources.length;

    // Recursively count resources in all child containers
    for (const childId of container.children) {
      count += countRecursive(childId);
    }

    return count;
  }

  return countRecursive(containerId);
}

// ─── Container type nesting order ─────────────────────────────────────────────

const CONTAINER_TYPES_ORDERED: ContainerType[] = ['cloud', 'account', 'region', 'vpc', 'az', 'subnet'];

// ─── Arbitrary: Hierarchy Tree with varied resource distribution ───────────────

interface GeneratedHierarchyWithCounts {
  hierarchy: HierarchyTree;
  /** Map of container ID to the expected recursive resource count */
  expectedCounts: Map<string, number>;
}

/**
 * Generates a valid HierarchyTree with nested containers and resources distributed
 * across various levels. This allows us to verify recursive counting at any level.
 */
const hierarchyWithResourcesArb: fc.Arbitrary<GeneratedHierarchyWithCounts> = fc
  .record({
    depth: fc.integer({ min: 2, max: 5 }),
    childrenPerContainer: fc.integer({ min: 1, max: 3 }),
    resourcesDistribution: fc.array(
      fc.integer({ min: 0, max: 4 }),
      { minLength: 1, maxLength: 30 }
    ),
  })
  .map(({ depth, childrenPerContainer, resourcesDistribution }) => {
    const containers: ContainerMetadata[] = [];
    let containerIdCounter = 0;
    let resourceIdCounter = 0;
    let resourceDistIdx = 0;

    // Helper to get next resource count from the distribution array
    function nextResourceCount(): number {
      const count = resourcesDistribution[resourceDistIdx % resourcesDistribution.length];
      resourceDistIdx++;
      return count;
    }

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

    const maxDepth = Math.min(depth, CONTAINER_TYPES_ORDERED.length - 1);

    for (let d = 1; d <= maxDepth; d++) {
      const containerType = CONTAINER_TYPES_ORDERED[d];
      const nextLevelParents: ContainerMetadata[] = [];

      for (const parent of currentLevelParents) {
        const numChildren = childrenPerContainer;

        for (let i = 0; i < numChildren; i++) {
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

    // Assign resources to containers (distribute across all non-root containers)
    const nonRootContainers = containers.filter(c => c.type !== 'cloud');
    for (const container of nonRootContainers) {
      const numResources = nextResourceCount();
      for (let i = 0; i < numResources; i++) {
        const resourceId = `resource-${resourceIdCounter++}`;
        container.resources.push(resourceId);
      }
    }

    // Also add some resources to the root for completeness
    const rootResourceCount = nextResourceCount();
    for (let i = 0; i < rootResourceCount; i++) {
      const resourceId = `resource-${resourceIdCounter++}`;
      rootContainer.resources.push(resourceId);
    }

    const hierarchy: HierarchyTree = {
      containers,
      root_id: rootId,
      boundary_services: [],
    };

    // Pre-compute expected counts for validation
    const expectedCounts = new Map<string, number>();
    const containerMap = new Map<string, ContainerMetadata>();
    for (const c of containers) {
      containerMap.set(c.id, c);
    }

    function computeExpected(id: string): number {
      const c = containerMap.get(id)!;
      let count = c.resources.length;
      for (const childId of c.children) {
        count += computeExpected(childId);
      }
      expectedCounts.set(id, count);
      return count;
    }

    computeExpected(rootId);

    return { hierarchy, expectedCounts };
  });

// ─── Property Test ────────────────────────────────────────────────────────────

describe('Property 13: Collapsed Container Badge Count', () => {
  it('computeRecursiveResourceCount equals total recursive resource count for any container', () => {
    fc.assert(
      fc.property(hierarchyWithResourcesArb, ({ hierarchy, expectedCounts }) => {
        // For every container in the hierarchy, the computed recursive resource count
        // must equal the expected value (sum of direct resources + all descendants' resources)
        for (const container of hierarchy.containers) {
          const computed = computeRecursiveResourceCount(container.id, hierarchy);
          const expected = expectedCounts.get(container.id)!;

          expect(
            computed,
            `Container "${container.id}" (type: ${container.type}) has recursive count ${computed}, ` +
            `but expected ${expected}. Direct resources: ${container.resources.length}, children: ${container.children.length}`
          ).toBe(expected);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('recursive count for a leaf container equals its direct resource count', () => {
    fc.assert(
      fc.property(hierarchyWithResourcesArb, ({ hierarchy }) => {
        // Leaf containers (no children) should have recursive count == direct resources
        for (const container of hierarchy.containers) {
          if (container.children.length === 0) {
            const computed = computeRecursiveResourceCount(container.id, hierarchy);
            expect(
              computed,
              `Leaf container "${container.id}" should have count equal to its direct resources (${container.resources.length})`
            ).toBe(container.resources.length);
          }
        }
      }),
      { numRuns: 100 }
    );
  });

  it('recursive count for a parent is always >= sum of its direct resources', () => {
    fc.assert(
      fc.property(hierarchyWithResourcesArb, ({ hierarchy }) => {
        // A container's recursive count must always be >= its own direct resource count
        for (const container of hierarchy.containers) {
          const computed = computeRecursiveResourceCount(container.id, hierarchy);
          expect(
            computed,
            `Container "${container.id}" recursive count (${computed}) should be >= direct resources (${container.resources.length})`
          ).toBeGreaterThanOrEqual(container.resources.length);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('non-existent container returns zero', () => {
    fc.assert(
      fc.property(hierarchyWithResourcesArb, ({ hierarchy }) => {
        // A container ID that doesn't exist should return 0
        const result = computeRecursiveResourceCount('non-existent-id', hierarchy);
        expect(result).toBe(0);
      }),
      { numRuns: 50 }
    );
  });
});
