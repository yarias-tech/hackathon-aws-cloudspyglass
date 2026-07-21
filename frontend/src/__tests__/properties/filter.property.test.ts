import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { DiagramNode, DiagramEdge, DiagramData } from '../../types/diagram';
import type { TagFilter, FilterCriteria, FilteredResult } from '../../types/filters';
import type { Resource } from '../../types/resources';

// ============================================================
// Pure filter logic functions (inline spec implementation)
// These define the expected behavior per the design document.
// ============================================================

/**
 * Apply tag filters with AND logic.
 * A resource matches if it has ALL specified tag key-value pairs.
 * Edges are included only if BOTH endpoints are in the filtered resource set.
 */
function applyTagFilters(
  resources: Resource[],
  edges: DiagramEdge[],
  tagFilters: TagFilter[]
): { filteredResources: Resource[]; filteredEdges: DiagramEdge[] } {
  if (tagFilters.length === 0) {
    return { filteredResources: resources, filteredEdges: edges };
  }

  const filteredResources = resources.filter((resource) =>
    tagFilters.every(
      (filter) => resource.tags[filter.key] === filter.value
    )
  );

  const filteredResourceIds = new Set(filteredResources.map((r) => r.arn));

  const filteredEdges = edges.filter(
    (edge) =>
      filteredResourceIds.has(edge.source) && filteredResourceIds.has(edge.target)
  );

  return { filteredResources, filteredEdges };
}

/**
 * Apply resource type filters with OR logic.
 * A resource matches if its type is ANY of the selected types.
 * Edges are included if at least one endpoint is in the filtered resource set.
 */
function applyTypeFilters(
  resources: Resource[],
  edges: DiagramEdge[],
  typeFilters: string[]
): { filteredResources: Resource[]; filteredEdges: DiagramEdge[] } {
  if (typeFilters.length === 0) {
    return { filteredResources: resources, filteredEdges: edges };
  }

  const typeSet = new Set(typeFilters);
  const filteredResources = resources.filter((r) => typeSet.has(r.resource_type));
  const filteredResourceIds = new Set(filteredResources.map((r) => r.arn));

  const filteredEdges = edges.filter(
    (edge) =>
      filteredResourceIds.has(edge.source) || filteredResourceIds.has(edge.target)
  );

  return { filteredResources, filteredEdges };
}

/**
 * Apply combined tag AND type filters (intersection).
 * A resource must satisfy ALL tag filters AND match at least one selected type.
 */
function applyCombinedFilters(
  resources: Resource[],
  edges: DiagramEdge[],
  tagFilters: TagFilter[],
  typeFilters: string[]
): { filteredResources: Resource[]; filteredEdges: DiagramEdge[] } {
  if (tagFilters.length === 0 && typeFilters.length === 0) {
    return { filteredResources: resources, filteredEdges: edges };
  }
  if (tagFilters.length === 0) {
    return applyTypeFilters(resources, edges, typeFilters);
  }
  if (typeFilters.length === 0) {
    return applyTagFilters(resources, edges, tagFilters);
  }

  const typeSet = new Set(typeFilters);

  const filteredResources = resources.filter(
    (resource) =>
      tagFilters.every((f) => resource.tags[f.key] === f.value) &&
      typeSet.has(resource.resource_type)
  );

  const filteredResourceIds = new Set(filteredResources.map((r) => r.arn));

  // Combined filter uses tag-filter edge logic (both endpoints must be in set)
  const filteredEdges = edges.filter(
    (edge) =>
      filteredResourceIds.has(edge.source) && filteredResourceIds.has(edge.target)
  );

  return { filteredResources, filteredEdges };
}

/**
 * Get available resource type filter options from a set of resources.
 */
function getAvailableTypeOptions(resources: Resource[]): Set<string> {
  return new Set(resources.map((r) => r.resource_type));
}

// ============================================================
// Arbitraries (generators)
// ============================================================

const resourceTypeArb = fc.constantFrom(
  'ec2', 'lambda', 's3', 'rds', 'vpc', 'subnet', 'security-group',
  'iam-role', 'alb', 'nlb', 'ecs', 'sns', 'sqs', 'dynamodb'
);

const edgeCategoryArb = fc.constantFrom(
  'network' as const,
  'iam' as const,
  'event' as const,
  'data' as const
);

const tagKeyArb = fc.stringOf(
  fc.constantFrom('Environment', 'Team', 'Project', 'Owner', 'CostCenter', 'App', 'Tier', 'Version'),
  { minLength: 1, maxLength: 1 }
).map((s) => s);

const tagValueArb = fc.constantFrom(
  'production', 'staging', 'development', 'platform', 'backend', 'frontend', 'v1', 'v2'
);

const tagFilterArb: fc.Arbitrary<TagFilter> = fc.record({
  key: fc.constantFrom('Environment', 'Team', 'Project', 'Owner', 'CostCenter', 'App', 'Tier', 'Version'),
  value: tagValueArb,
});

const tagsArb: fc.Arbitrary<Record<string, string>> = fc.dictionary(
  fc.constantFrom('Environment', 'Team', 'Project', 'Owner', 'CostCenter', 'App', 'Tier', 'Version'),
  tagValueArb,
  { minKeys: 0, maxKeys: 5 }
);

const resourceArb: fc.Arbitrary<Resource> = fc.record({
  arn: fc.uuid().map((id) => `arn:aws:ec2:us-east-1:123456789012:resource/${id}`),
  resource_type: resourceTypeArb,
  name: fc.string({ minLength: 1, maxLength: 20 }),
  region: fc.constantFrom('us-east-1', 'us-west-2', 'eu-west-1'),
  tags: tagsArb,
  creation_date: fc.constant(null),
  iam_role: fc.constant(null),
  attributes: fc.constant({}),
  is_external: fc.boolean(),
  is_unresolved: fc.boolean(),
});

function edgesFromResources(resources: Resource[]): fc.Arbitrary<DiagramEdge[]> {
  if (resources.length < 2) {
    return fc.constant([]);
  }
  const indexArb = fc.nat({ max: resources.length - 1 });
  const edgeArb = fc.tuple(indexArb, indexArb, edgeCategoryArb, fc.uuid()).filter(
    ([s, t]) => s !== t
  ).map(([sourceIdx, targetIdx, category, id]) => ({
    id,
    source: resources[sourceIdx].arn,
    target: resources[targetIdx].arn,
    category,
    derived_from: 'test',
    label: null,
  }));

  return fc.array(edgeArb, { minLength: 0, maxLength: Math.min(resources.length * 2, 20) });
}

// ============================================================
// Property Tests
// ============================================================

/**
 * **Validates: Requirements 7.1, 7.3, 7.4**
 *
 * Property 14: Tag filter AND logic with edge filtering
 */
describe('Property 14: Tag filter AND logic with edge filtering', () => {
  it('filtered result contains ONLY resources matching ALL tag criteria', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 15 }),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 5 }),
        (resources, tagFilters) => {
          const { filteredResources } = applyTagFilters(resources, [], tagFilters);

          // Every filtered resource must match ALL tag filters
          for (const resource of filteredResources) {
            for (const filter of tagFilters) {
              expect(resource.tags[filter.key]).toBe(filter.value);
            }
          }

          // Every resource NOT in filtered set must fail at least one tag filter
          const filteredArns = new Set(filteredResources.map((r) => r.arn));
          for (const resource of resources) {
            if (!filteredArns.has(resource.arn)) {
              const matchesAll = tagFilters.every(
                (f) => resource.tags[f.key] === f.value
              );
              expect(matchesAll).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('filtered edges include ONLY edges where BOTH endpoints are in filtered set', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 2, maxLength: 10 }).chain((resources) =>
          edgesFromResources(resources).map((edges) => ({ resources, edges }))
        ),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 3 }),
        ({ resources, edges }, tagFilters) => {
          const { filteredResources, filteredEdges } = applyTagFilters(
            resources, edges, tagFilters
          );
          const filteredIds = new Set(filteredResources.map((r) => r.arn));

          // Every filtered edge must have BOTH endpoints in filtered set
          for (const edge of filteredEdges) {
            expect(filteredIds.has(edge.source)).toBe(true);
            expect(filteredIds.has(edge.target)).toBe(true);
          }

          // Every edge NOT in filtered set must have at least one endpoint outside filtered set
          const filteredEdgeIds = new Set(filteredEdges.map((e) => e.id));
          for (const edge of edges) {
            if (!filteredEdgeIds.has(edge.id)) {
              const bothInSet = filteredIds.has(edge.source) && filteredIds.has(edge.target);
              expect(bothInSet).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('filtered_count <= total_count', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 0, maxLength: 20 }),
        fc.array(tagFilterArb, { minLength: 0, maxLength: 5 }),
        (resources, tagFilters) => {
          const { filteredResources } = applyTagFilters(resources, [], tagFilters);
          expect(filteredResources.length).toBeLessThanOrEqual(resources.length);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * **Validates: Requirements 7.6**
 *
 * Property 16: Filter removal round-trip
 */
describe('Property 16: Filter removal round-trip', () => {
  it('applying then removing tag filters produces original result', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 10 }).chain((resources) =>
          edgesFromResources(resources).map((edges) => ({ resources, edges }))
        ),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 5 }),
        ({ resources, edges }, tagFilters) => {
          // Apply filters
          applyTagFilters(resources, edges, tagFilters);

          // Remove filters (apply with empty filter list)
          const { filteredResources, filteredEdges } = applyTagFilters(resources, edges, []);

          // Result should be equivalent to original
          expect(filteredResources).toEqual(resources);
          expect(filteredEdges).toEqual(edges);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('applying then removing type filters produces original result', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 10 }).chain((resources) =>
          edgesFromResources(resources).map((edges) => ({ resources, edges }))
        ),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 5 }),
        ({ resources, edges }, typeFilters) => {
          // Apply filters
          applyTypeFilters(resources, edges, typeFilters);

          // Remove filters (apply with empty filter list)
          const { filteredResources, filteredEdges } = applyTypeFilters(resources, edges, []);

          // Result should be equivalent to original
          expect(filteredResources).toEqual(resources);
          expect(filteredEdges).toEqual(edges);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('applying then removing combined filters produces original result', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 10 }).chain((resources) =>
          edgesFromResources(resources).map((edges) => ({ resources, edges }))
        ),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 3 }),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 3 }),
        ({ resources, edges }, tagFilters, typeFilters) => {
          // Apply combined filters
          applyCombinedFilters(resources, edges, tagFilters, typeFilters);

          // Remove all filters
          const { filteredResources, filteredEdges } = applyCombinedFilters(
            resources, edges, [], []
          );

          // Result should be equivalent to original
          expect(filteredResources).toEqual(resources);
          expect(filteredEdges).toEqual(edges);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * **Validates: Requirements 8.1**
 *
 * Property 17: Resource type filter available options
 */
describe('Property 17: Resource type filter available options', () => {
  it('available type options equal the set of distinct resource_type values in data', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 20 }),
        (resources) => {
          const availableOptions = getAvailableTypeOptions(resources);
          const expectedTypes = new Set(resources.map((r) => r.resource_type));

          // Sets should be exactly equal
          expect(availableOptions.size).toBe(expectedTypes.size);
          for (const type of expectedTypes) {
            expect(availableOptions.has(type)).toBe(true);
          }
          for (const type of availableOptions) {
            expect(expectedTypes.has(type)).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('empty resource list produces empty type options', () => {
    const availableOptions = getAvailableTypeOptions([]);
    expect(availableOptions.size).toBe(0);
  });
});

/**
 * **Validates: Requirements 8.2**
 *
 * Property 18: Resource type OR logic with edge visibility
 */
describe('Property 18: Resource type OR logic with edge visibility', () => {
  it('filtered result contains all resources matching ANY selected type', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 15 }),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 5 }),
        (resources, typeFilters) => {
          const typeSet = new Set(typeFilters);
          const { filteredResources } = applyTypeFilters(resources, [], typeFilters);
          const filteredArns = new Set(filteredResources.map((r) => r.arn));

          // Every resource matching a selected type must be in filtered set
          for (const resource of resources) {
            if (typeSet.has(resource.resource_type)) {
              expect(filteredArns.has(resource.arn)).toBe(true);
            }
          }

          // Every filtered resource must match at least one selected type
          for (const resource of filteredResources) {
            expect(typeSet.has(resource.resource_type)).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('edges are included if at least one endpoint is a resource of a selected type', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 2, maxLength: 10 }).chain((resources) =>
          edgesFromResources(resources).map((edges) => ({ resources, edges }))
        ),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 4 }),
        ({ resources, edges }, typeFilters) => {
          const { filteredResources, filteredEdges } = applyTypeFilters(
            resources, edges, typeFilters
          );
          const filteredIds = new Set(filteredResources.map((r) => r.arn));

          // Every filtered edge must have at least one endpoint in the filtered set
          for (const edge of filteredEdges) {
            const hasEndpointInSet =
              filteredIds.has(edge.source) || filteredIds.has(edge.target);
            expect(hasEndpointInSet).toBe(true);
          }

          // Every edge NOT in filtered set must have NEITHER endpoint in filtered set
          const filteredEdgeIds = new Set(filteredEdges.map((e) => e.id));
          for (const edge of edges) {
            if (!filteredEdgeIds.has(edge.id)) {
              const hasEndpoint =
                filteredIds.has(edge.source) || filteredIds.has(edge.target);
              expect(hasEndpoint).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * **Validates: Requirements 8.5**
 *
 * Property 19: Combined filter intersection
 */
describe('Property 19: Combined filter intersection', () => {
  it('result contains only resources satisfying ALL tag filters AND matching at least one type', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 15 }),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 3 }),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 4 }),
        (resources, tagFilters, typeFilters) => {
          const typeSet = new Set(typeFilters);
          const { filteredResources } = applyCombinedFilters(
            resources, [], tagFilters, typeFilters
          );

          // Every filtered resource must satisfy ALL conditions
          for (const resource of filteredResources) {
            // Must match all tag filters
            for (const filter of tagFilters) {
              expect(resource.tags[filter.key]).toBe(filter.value);
            }
            // Must match at least one type filter
            expect(typeSet.has(resource.resource_type)).toBe(true);
          }

          // Every resource NOT in filtered set must fail at least one condition
          const filteredArns = new Set(filteredResources.map((r) => r.arn));
          for (const resource of resources) {
            if (!filteredArns.has(resource.arn)) {
              const matchesAllTags = tagFilters.every(
                (f) => resource.tags[f.key] === f.value
              );
              const matchesType = typeSet.has(resource.resource_type);
              // Must fail at least one: either tags or type
              expect(matchesAllTags && matchesType).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('combined filter result is subset of both tag-only and type-only results', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 10 }),
        fc.array(tagFilterArb, { minLength: 1, maxLength: 3 }),
        fc.array(resourceTypeArb, { minLength: 1, maxLength: 3 }),
        (resources, tagFilters, typeFilters) => {
          const { filteredResources: tagOnly } = applyTagFilters(resources, [], tagFilters);
          const { filteredResources: typeOnly } = applyTypeFilters(resources, [], typeFilters);
          const { filteredResources: combined } = applyCombinedFilters(
            resources, [], tagFilters, typeFilters
          );

          const tagOnlyArns = new Set(tagOnly.map((r) => r.arn));
          const typeOnlyArns = new Set(typeOnly.map((r) => r.arn));

          // Combined must be a subset of both tag-only and type-only
          for (const resource of combined) {
            expect(tagOnlyArns.has(resource.arn)).toBe(true);
            expect(typeOnlyArns.has(resource.arn)).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
