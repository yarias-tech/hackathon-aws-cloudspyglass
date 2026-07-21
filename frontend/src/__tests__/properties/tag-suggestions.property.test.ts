import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { TagSuggestion } from '../../types/filters';
import type { Resource } from '../../types/resources';

// ============================================================
// Pure tag suggestion logic (inline spec implementation)
// Mirrors the backend get_tag_suggestions behavior per the design document.
// ============================================================

/**
 * Compute tag suggestions from a list of resources.
 * Returns up to 20 tag key-value pairs ordered by descending frequency,
 * with alphabetical tiebreaking on key then value.
 * Optionally filters by a prefix (case-insensitive startsWith on key or value).
 */
function getTagSuggestions(
  resources: Resource[],
  prefix: string
): TagSuggestion[] {
  // Count frequency of each (key, value) pair across all resources
  const tagCounter = new Map<string, number>();

  for (const resource of resources) {
    for (const [key, value] of Object.entries(resource.tags)) {
      const compositeKey = `${key}\0${value}`;
      tagCounter.set(compositeKey, (tagCounter.get(compositeKey) ?? 0) + 1);
    }
  }

  // Filter by prefix (case-insensitive startsWith on key or value)
  const prefixLower = prefix.toLowerCase();
  const filtered: Array<{ key: string; value: string; count: number }> = [];

  for (const [compositeKey, count] of tagCounter.entries()) {
    const [key, value] = compositeKey.split('\0');
    if (
      prefixLower === '' ||
      key.toLowerCase().startsWith(prefixLower) ||
      value.toLowerCase().startsWith(prefixLower)
    ) {
      filtered.push({ key, value, count });
    }
  }

  // Sort by descending frequency, then alphabetically by key, then value
  filtered.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    if (a.key !== b.key) return a.key < b.key ? -1 : 1;
    return a.value < b.value ? -1 : a.value > b.value ? 1 : 0;
  });

  // Return top 20
  return filtered.slice(0, 20);
}

// ============================================================
// Arbitraries (generators)
// ============================================================

const tagKeyArb = fc.constantFrom(
  'Environment', 'Team', 'Project', 'Owner', 'CostCenter',
  'App', 'Tier', 'Version', 'Service', 'Department',
  'Stack', 'Stage', 'Component', 'Managed', 'Purpose'
);

const tagValueArb = fc.constantFrom(
  'production', 'staging', 'development', 'platform', 'backend',
  'frontend', 'v1', 'v2', 'data', 'infra', 'core', 'shared',
  'alpha', 'beta', 'gamma', 'delta', 'ops', 'security'
);

const tagsArb: fc.Arbitrary<Record<string, string>> = fc.dictionary(
  tagKeyArb,
  tagValueArb,
  { minKeys: 0, maxKeys: 6 }
);

const resourceArb: fc.Arbitrary<Resource> = fc.record({
  arn: fc.uuid().map((id) => `arn:aws:ec2:us-east-1:123456789012:resource/${id}`),
  resource_type: fc.constantFrom('ec2', 'lambda', 's3', 'rds', 'vpc', 'subnet'),
  name: fc.string({ minLength: 1, maxLength: 20 }),
  region: fc.constantFrom('us-east-1', 'us-west-2', 'eu-west-1'),
  tags: tagsArb,
  creation_date: fc.constant(null),
  iam_role: fc.constant(null),
  attributes: fc.constant({}),
  is_external: fc.boolean(),
  is_unresolved: fc.boolean(),
});

const prefixArb = fc.oneof(
  fc.constant(''),
  fc.constantFrom('Env', 'env', 'Team', 'team', 'pro', 'Pro', 'v', 'V', 'st', 'St')
);

// ============================================================
// Property Tests
// ============================================================

/**
 * **Validates: Requirements 7.2**
 *
 * Property 15: Tag autocomplete frequency ordering
 */
describe('Property 15: Tag autocomplete frequency ordering', () => {
  it('tag suggestion list returns at most 20 entries', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 30 }),
        prefixArb,
        (resources, prefix) => {
          const suggestions = getTagSuggestions(resources, prefix);
          expect(suggestions.length).toBeLessThanOrEqual(20);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('suggestions are ordered by descending frequency (count[i] >= count[i+1])', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 30 }),
        prefixArb,
        (resources, prefix) => {
          const suggestions = getTagSuggestions(resources, prefix);

          for (let i = 0; i < suggestions.length - 1; i++) {
            expect(suggestions[i].count).toBeGreaterThanOrEqual(suggestions[i + 1].count);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('count for each suggestion equals actual number of resources with that (key, value) pair', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 20 }),
        prefixArb,
        (resources, prefix) => {
          const suggestions = getTagSuggestions(resources, prefix);

          for (const suggestion of suggestions) {
            const actualCount = resources.filter(
              (r) => r.tags[suggestion.key] === suggestion.value
            ).length;
            expect(suggestion.count).toBe(actualCount);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('if more than 20 distinct tag key-value pairs exist, only the top 20 by frequency are returned', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 5, maxLength: 40 }),
        (resources) => {
          const suggestions = getTagSuggestions(resources, '');

          // Count all distinct tag pairs
          const allPairs = new Set<string>();
          for (const resource of resources) {
            for (const [key, value] of Object.entries(resource.tags)) {
              allPairs.add(`${key}\0${value}`);
            }
          }

          if (allPairs.size > 20) {
            expect(suggestions.length).toBe(20);

            // Verify we got the top 20: the minimum count in our results
            // should be >= any count NOT in our results
            const returnedKeys = new Set(
              suggestions.map((s) => `${s.key}\0${s.value}`)
            );
            const minReturnedCount = Math.min(...suggestions.map((s) => s.count));

            // Count all (key, value) pairs not returned
            const tagCounter = new Map<string, number>();
            for (const resource of resources) {
              for (const [key, value] of Object.entries(resource.tags)) {
                const ck = `${key}\0${value}`;
                tagCounter.set(ck, (tagCounter.get(ck) ?? 0) + 1);
              }
            }

            for (const [ck, count] of tagCounter.entries()) {
              if (!returnedKeys.has(ck)) {
                expect(minReturnedCount).toBeGreaterThanOrEqual(count);
              }
            }
          } else {
            expect(suggestions.length).toBe(allPairs.size);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('empty prefix returns suggestions from all tags', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 20 }),
        (resources) => {
          const suggestionsEmpty = getTagSuggestions(resources, '');

          // Count all distinct tag pairs
          const allPairs = new Set<string>();
          for (const resource of resources) {
            for (const [key, value] of Object.entries(resource.tags)) {
              allPairs.add(`${key}\0${value}`);
            }
          }

          // With empty prefix, we should get min(allPairs.size, 20) suggestions
          expect(suggestionsEmpty.length).toBe(Math.min(allPairs.size, 20));
        }
      ),
      { numRuns: 100 }
    );
  });

  it('prefix filtering matches against key or value (case-insensitive startsWith)', () => {
    fc.assert(
      fc.property(
        fc.array(resourceArb, { minLength: 1, maxLength: 20 }),
        prefixArb.filter((p) => p.length > 0),
        (resources, prefix) => {
          const suggestions = getTagSuggestions(resources, prefix);
          const prefixLower = prefix.toLowerCase();

          // Every returned suggestion must have key or value starting with prefix
          for (const suggestion of suggestions) {
            const keyMatches = suggestion.key.toLowerCase().startsWith(prefixLower);
            const valueMatches = suggestion.value.toLowerCase().startsWith(prefixLower);
            expect(keyMatches || valueMatches).toBe(true);
          }

          // Every tag pair in the data that matches the prefix and has high enough
          // frequency should be in the results (unless bumped out by top-20 cutoff)
          const tagCounter = new Map<string, number>();
          for (const resource of resources) {
            for (const [key, value] of Object.entries(resource.tags)) {
              const ck = `${key}\0${value}`;
              tagCounter.set(ck, (tagCounter.get(ck) ?? 0) + 1);
            }
          }

          const matchingPairs: Array<{ key: string; value: string; count: number }> = [];
          for (const [ck, count] of tagCounter.entries()) {
            const [key, value] = ck.split('\0');
            if (
              key.toLowerCase().startsWith(prefixLower) ||
              value.toLowerCase().startsWith(prefixLower)
            ) {
              matchingPairs.push({ key, value, count });
            }
          }

          // Suggestions length should be min(matchingPairs.length, 20)
          expect(suggestions.length).toBe(Math.min(matchingPairs.length, 20));
        }
      ),
      { numRuns: 100 }
    );
  });
});
