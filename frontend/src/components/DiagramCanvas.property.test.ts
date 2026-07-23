// Feature: architecture-diagram-visualization, Property 14: Edge Rerouting on Collapse
import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { Edge } from '@xyflow/react';
import type { ContainerMetadata } from '../types/hierarchy';
import { rerouteEdgesForCollapsedContainers } from './DiagramCanvas';

/**
 * **Validates: Requirements 8.9**
 *
 * Property 14: Edge Rerouting on Collapse
 * When containers are collapsed, edges whose source or target is a resource
 * inside the collapsed container are rerouted to point to the container node.
 * The total logical relationship set remains represented (count may decrease
 * due to deduplication and self-loop removal, but no new edges are introduced).
 */

// ─── Generators ───────────────────────────────────────────────────────────────

/**
 * Generates a test scenario with containers, resources, edges, and a set of
 * collapsed containers.
 */
interface EdgeRerouteScenario {
  edges: Edge[];
  collapsedContainers: Set<string>;
  containerMap: Map<string, ContainerMetadata>;
  /** All resource IDs that belong to collapsed containers */
  collapsedResourceIds: Set<string>;
  /** All resource IDs across all containers */
  allResourceIds: string[];
}

const edgeRerouteScenarioArb: fc.Arbitrary<EdgeRerouteScenario> = fc
  .record({
    numContainers: fc.integer({ min: 1, max: 5 }),
    resourcesPerContainer: fc.integer({ min: 1, max: 4 }),
    numEdges: fc.integer({ min: 1, max: 12 }),
    numCollapsed: fc.integer({ min: 1, max: 3 }),
    edgeCategories: fc.array(
      fc.constantFrom('network', 'iam', 'event', 'data', 'other'),
      { minLength: 1, maxLength: 12 }
    ),
  })
  .map(({ numContainers, resourcesPerContainer, numEdges, numCollapsed, edgeCategories }) => {
    const containerMap = new Map<string, ContainerMetadata>();
    const allResourceIds: string[] = [];

    // Create containers with resources
    for (let c = 0; c < numContainers; c++) {
      const containerId = `container-${c}`;
      const resources: string[] = [];
      for (let r = 0; r < resourcesPerContainer; r++) {
        const resId = `res-${c}-${r}`;
        resources.push(resId);
        allResourceIds.push(resId);
      }
      containerMap.set(containerId, {
        id: containerId,
        name: `Container ${c}`,
        type: 'vpc',
        parent_id: null,
        subnet_type: null,
        icon_key: 'icon-vpc',
        resources,
        children: [],
      });
    }

    // Select which containers to collapse (up to numCollapsed, but not more than available)
    const containerIds = Array.from(containerMap.keys());
    const actualCollapsed = Math.min(numCollapsed, containerIds.length);
    const collapsedContainers = new Set<string>(containerIds.slice(0, actualCollapsed));

    // Build set of resource IDs inside collapsed containers
    const collapsedResourceIds = new Set<string>();
    for (const containerId of collapsedContainers) {
      const container = containerMap.get(containerId)!;
      for (const resId of container.resources) {
        collapsedResourceIds.add(resId);
      }
    }

    // Generate edges between random resources
    const edges: Edge[] = [];
    const actualNumEdges = Math.min(numEdges, allResourceIds.length * allResourceIds.length);
    for (let e = 0; e < actualNumEdges; e++) {
      const sourceIdx = e % allResourceIds.length;
      const targetIdx = (e + 1 + Math.floor(e / allResourceIds.length)) % allResourceIds.length;
      if (sourceIdx === targetIdx) continue;
      const category = edgeCategories[e % edgeCategories.length];
      edges.push({
        id: `edge-${e}`,
        source: allResourceIds[sourceIdx],
        target: allResourceIds[targetIdx],
        data: { category },
      });
    }

    return {
      edges,
      collapsedContainers,
      containerMap,
      collapsedResourceIds,
      allResourceIds,
    };
  });

/**
 * Generator for scenarios where no containers are collapsed.
 */
const noCollapseScenarioArb: fc.Arbitrary<EdgeRerouteScenario> = fc
  .record({
    numContainers: fc.integer({ min: 1, max: 4 }),
    resourcesPerContainer: fc.integer({ min: 1, max: 3 }),
    numEdges: fc.integer({ min: 1, max: 8 }),
  })
  .map(({ numContainers, resourcesPerContainer, numEdges }) => {
    const containerMap = new Map<string, ContainerMetadata>();
    const allResourceIds: string[] = [];

    for (let c = 0; c < numContainers; c++) {
      const containerId = `container-${c}`;
      const resources: string[] = [];
      for (let r = 0; r < resourcesPerContainer; r++) {
        const resId = `res-${c}-${r}`;
        resources.push(resId);
        allResourceIds.push(resId);
      }
      containerMap.set(containerId, {
        id: containerId,
        name: `Container ${c}`,
        type: 'subnet',
        parent_id: null,
        subnet_type: 'private',
        icon_key: 'icon-subnet',
        resources,
        children: [],
      });
    }

    const edges: Edge[] = [];
    for (let e = 0; e < Math.min(numEdges, allResourceIds.length - 1); e++) {
      edges.push({
        id: `edge-${e}`,
        source: allResourceIds[e % allResourceIds.length],
        target: allResourceIds[(e + 1) % allResourceIds.length],
        data: { category: 'network' },
      });
    }

    return {
      edges,
      collapsedContainers: new Set<string>(),
      containerMap,
      collapsedResourceIds: new Set<string>(),
      allResourceIds,
    };
  });

/**
 * Generator for edges where source and target are OUTSIDE any collapsed container.
 */
const outsideEdgesScenarioArb: fc.Arbitrary<EdgeRerouteScenario> = fc
  .record({
    numEdges: fc.integer({ min: 1, max: 6 }),
  })
  .map(({ numEdges }) => {
    const containerMap = new Map<string, ContainerMetadata>();

    // Container A (will be collapsed) with resources
    containerMap.set('container-collapsed', {
      id: 'container-collapsed',
      name: 'Collapsed',
      type: 'vpc',
      parent_id: null,
      subnet_type: null,
      icon_key: 'icon-vpc',
      resources: ['res-collapsed-0', 'res-collapsed-1'],
      children: [],
    });

    // Container B (NOT collapsed) with resources
    containerMap.set('container-open', {
      id: 'container-open',
      name: 'Open',
      type: 'subnet',
      parent_id: null,
      subnet_type: 'public',
      icon_key: 'icon-subnet',
      resources: ['res-open-0', 'res-open-1', 'res-open-2'],
      children: [],
    });

    const collapsedContainers = new Set(['container-collapsed']);
    const outsideResources = ['res-open-0', 'res-open-1', 'res-open-2'];

    // Generate edges only between outside resources
    const edges: Edge[] = [];
    for (let e = 0; e < Math.min(numEdges, 3); e++) {
      edges.push({
        id: `edge-${e}`,
        source: outsideResources[e % outsideResources.length],
        target: outsideResources[(e + 1) % outsideResources.length],
        data: { category: 'data' },
      });
    }

    return {
      edges,
      collapsedContainers,
      containerMap,
      collapsedResourceIds: new Set(['res-collapsed-0', 'res-collapsed-1']),
      allResourceIds: ['res-collapsed-0', 'res-collapsed-1', 'res-open-0', 'res-open-1', 'res-open-2'],
    };
  });

// ─── Property Tests ───────────────────────────────────────────────────────────

describe('Property 14: Edge Rerouting on Collapse', () => {
  it('edges involving collapsed resources are rerouted to the container node', () => {
    fc.assert(
      fc.property(edgeRerouteScenarioArb, (scenario) => {
        const { edges, collapsedContainers, containerMap, collapsedResourceIds } = scenario;
        const result = rerouteEdgesForCollapsedContainers(edges, collapsedContainers, containerMap);

        // Every rerouted edge should have source/target pointing to either:
        // - A non-collapsed resource (unchanged)
        // - A collapsed container ID (rerouted)
        for (const edge of result) {
          // Source should not be a resource inside a collapsed container
          expect(
            collapsedResourceIds.has(edge.source),
            `Edge source "${edge.source}" should not be a resource inside a collapsed container`
          ).toBe(false);
          // Target should not be a resource inside a collapsed container
          expect(
            collapsedResourceIds.has(edge.target),
            `Edge target "${edge.target}" should not be a resource inside a collapsed container`
          ).toBe(false);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('no new edges are introduced that were not represented in the original set', () => {
    fc.assert(
      fc.property(edgeRerouteScenarioArb, (scenario) => {
        const { edges, collapsedContainers, containerMap } = scenario;
        const result = rerouteEdgesForCollapsedContainers(edges, collapsedContainers, containerMap);

        // Result count should be <= original count (dedup + self-loop removal)
        expect(result.length).toBeLessThanOrEqual(edges.length);

        // Every edge in the result must trace back to an original edge
        // (either unchanged or rerouted from an original)
        for (const rEdge of result) {
          const baseId = rEdge.id.replace('__rerouted', '');
          const originalExists = edges.some((e) => e.id === baseId);
          expect(
            originalExists,
            `Rerouted edge "${rEdge.id}" has no corresponding original edge`
          ).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('no collapse means edges returned unchanged', () => {
    fc.assert(
      fc.property(noCollapseScenarioArb, (scenario) => {
        const { edges, collapsedContainers, containerMap } = scenario;
        const result = rerouteEdgesForCollapsedContainers(edges, collapsedContainers, containerMap);

        // With no collapsed containers, output should be identical to input
        expect(result).toEqual(edges);
      }),
      { numRuns: 100 }
    );
  });

  it('edges not involving collapsed containers remain unchanged', () => {
    fc.assert(
      fc.property(outsideEdgesScenarioArb, (scenario) => {
        const { edges, collapsedContainers, containerMap } = scenario;
        const result = rerouteEdgesForCollapsedContainers(edges, collapsedContainers, containerMap);

        // Edges between resources outside collapsed containers should be unchanged
        for (const edge of edges) {
          const matchingResult = result.find((r) => r.id === edge.id);
          expect(
            matchingResult,
            `Edge "${edge.id}" between outside resources should remain in result`
          ).toBeDefined();
          expect(matchingResult!.source).toBe(edge.source);
          expect(matchingResult!.target).toBe(edge.target);
        }
      }),
      { numRuns: 100 }
    );
  });
});
