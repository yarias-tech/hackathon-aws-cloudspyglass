import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import {
  EDGE_STYLES,
  DEFAULT_EDGE_STYLE,
  getEdgeStyle,
  truncateLabel,
  createEdgesFromRelationships,
} from './RelationshipEdge';

/**
 * // Feature: architecture-diagram-visualization, Property 7: Edge Category-to-Style Mapping
 *
 * **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.9**
 *
 * For any diagram edge, the rendered style (color and line pattern) SHALL be
 * deterministically determined by its category: "network" → blue/solid,
 * "iam" → red/dashed, "event" → orange/dotted, "data" → purple/solid,
 * and any other category → gray/solid.
 */
describe('Property 7: Edge Category-to-Style Mapping', () => {
  /** Expected styling per the design specification */
  const EXPECTED_STYLES: Record<
    string,
    { stroke: string; dasharray: string | undefined; animated: boolean }
  > = {
    network: { stroke: '#2563EB', dasharray: undefined, animated: false },
    iam: { stroke: '#DC2626', dasharray: '5 5', animated: false },
    event: { stroke: '#EA580C', dasharray: '2 2', animated: true },
    data: { stroke: '#7C3AED', dasharray: undefined, animated: false },
  };

  const knownCategoryArb = fc.constantFrom(
    'network' as const,
    'iam' as const,
    'event' as const,
    'data' as const
  );

  const unknownCategoryArb = fc.string({ minLength: 1 }).filter(
    (s) => !['network', 'iam', 'event', 'data'].includes(s)
  );

  it('each known category maps to the correct color, dash style, and animation', () => {
    fc.assert(
      fc.property(knownCategoryArb, (category) => {
        const style = getEdgeStyle(category);
        const expected = EXPECTED_STYLES[category];

        expect(style.stroke).toBe(expected.stroke);
        expect(style.strokeDasharray).toBe(expected.dasharray);
        expect(style.animated).toBe(expected.animated);
      }),
      { numRuns: 100 }
    );
  });

  it('unknown categories always get gray/solid default style', () => {
    fc.assert(
      fc.property(unknownCategoryArb, (category) => {
        const style = getEdgeStyle(category);

        expect(style.stroke).toBe('#6B7280');
        expect(style.strokeDasharray).toBeUndefined();
        expect(style.animated).toBe(false);
        expect(style).toBe(DEFAULT_EDGE_STYLE);
      }),
      { numRuns: 100 }
    );
  });

  it('all known categories have distinct colors (no two share a color)', () => {
    fc.assert(
      fc.property(
        knownCategoryArb,
        knownCategoryArb,
        (catA, catB) => {
          if (catA !== catB) {
            expect(getEdgeStyle(catA).stroke).not.toBe(getEdgeStyle(catB).stroke);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('only event category has animation enabled among known categories', () => {
    fc.assert(
      fc.property(knownCategoryArb, (category) => {
        if (category === 'event') {
          expect(getEdgeStyle(category).animated).toBe(true);
        } else {
          expect(getEdgeStyle(category).animated).toBe(false);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('style mapping is deterministic (same category always produces same result)', () => {
    fc.assert(
      fc.property(
        fc.oneof(knownCategoryArb, unknownCategoryArb),
        (category) => {
          const style1 = getEdgeStyle(category);
          const style2 = getEdgeStyle(category);
          expect(style1).toBe(style2);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('solid categories (network, data, unknown) have no strokeDasharray', () => {
    const solidKnown = ['network', 'data'] as const;

    fc.assert(
      fc.property(fc.constantFrom(...solidKnown), (category) => {
        expect(getEdgeStyle(category).strokeDasharray).toBeUndefined();
      }),
      { numRuns: 50 }
    );
  });

  it('non-solid categories (iam, event) have strokeDasharray defined', () => {
    const nonSolidCategories = ['iam', 'event'] as const;

    fc.assert(
      fc.property(fc.constantFrom(...nonSolidCategories), (category) => {
        expect(getEdgeStyle(category).strokeDasharray).toBeDefined();
      }),
      { numRuns: 50 }
    );
  });

  it('EDGE_STYLES covers exactly the 4 known categories', () => {
    const requiredCategories = new Set(['network', 'iam', 'event', 'data']);
    const actualCategories = new Set(Object.keys(EDGE_STYLES));

    for (const required of requiredCategories) {
      expect(actualCategories.has(required)).toBe(true);
    }

    expect(actualCategories.size).toBe(4);
  });
});

/**
 * // Feature: architecture-diagram-visualization, Property 8: Edge Label Truncation
 *
 * **Validates: Requirements 4.6**
 *
 * For any edge label string, if its length exceeds 40 characters the displayed
 * text SHALL be the first 40 characters followed by "…" (total displayed length 41);
 * if its length is 40 or fewer characters the full text SHALL be displayed unmodified.
 */
describe('Property 8: Edge Label Truncation', () => {
  const shortLabelArb = fc.string({ minLength: 0, maxLength: 40 });
  const longLabelArb = fc.string({ minLength: 41, maxLength: 200 });

  it('labels of 40 chars or fewer are returned unmodified', () => {
    fc.assert(
      fc.property(shortLabelArb, (label) => {
        const result = truncateLabel(label);
        expect(result).toBe(label);
      }),
      { numRuns: 100 }
    );
  });

  it('labels longer than 40 chars are truncated to first 40 + ellipsis', () => {
    fc.assert(
      fc.property(longLabelArb, (label) => {
        const result = truncateLabel(label);
        expect(result.length).toBe(41);
        expect(result).toBe(label.slice(0, 40) + '\u2026');
        expect(result.endsWith('\u2026')).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it('truncated label preserves the first 40 characters exactly', () => {
    fc.assert(
      fc.property(longLabelArb, (label) => {
        const result = truncateLabel(label);
        expect(result.slice(0, 40)).toBe(label.slice(0, 40));
      }),
      { numRuns: 100 }
    );
  });

  it('truncateLabel is a pure function (same input always same output)', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 0, maxLength: 200 }), (label) => {
        const result1 = truncateLabel(label);
        const result2 = truncateLabel(label);
        expect(result1).toBe(result2);
      }),
      { numRuns: 100 }
    );
  });
});

/**
 * // Feature: architecture-diagram-visualization, Property 9: Edge Count Matches Relationships
 *
 * **Validates: Requirements 4.1**
 *
 * For any set of relationships provided to the diagram, the rendered edge set SHALL
 * contain exactly one directed edge per relationship, with source and target matching
 * the relationship's source and target respectively.
 */
describe('Property 9: Edge Count Matches Relationships', () => {
  /** Arbitrary for a valid edge category */
  const categoryArb = fc.constantFrom(
    'network' as const,
    'iam' as const,
    'event' as const,
    'data' as const
  );

  /** Arbitrary for a single DiagramEdge-like object */
  const diagramEdgeArb = fc.record({
    id: fc.uuid(),
    source: fc.string({ minLength: 1, maxLength: 100 }),
    target: fc.string({ minLength: 1, maxLength: 100 }),
    category: categoryArb,
    derived_from: fc.string({ minLength: 0, maxLength: 100 }),
    label: fc.oneof(fc.constant(null), fc.string({ minLength: 0, maxLength: 100 })),
  });

  /** Arbitrary for a set of DiagramEdges of varying sizes (0 to 50) */
  const diagramEdgesArb = fc.array(diagramEdgeArb, { minLength: 0, maxLength: 50 });

  it('output edge count equals input relationship count', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        expect(result.length).toBe(edges.length);
      }),
      { numRuns: 100 }
    );
  });

  it('each output edge source matches input relationship source', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        for (let i = 0; i < edges.length; i++) {
          expect(result[i].source).toBe(edges[i].source);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('each output edge target matches input relationship target', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        for (let i = 0; i < edges.length; i++) {
          expect(result[i].target).toBe(edges[i].target);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('each output edge has type "relationship"', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        for (const edge of result) {
          expect(edge.type).toBe('relationship');
        }
      }),
      { numRuns: 100 }
    );
  });

  it('each output edge preserves the id from the input relationship', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        for (let i = 0; i < edges.length; i++) {
          expect(result[i].id).toBe(edges[i].id);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('each output edge data contains category and derivedFrom from input', () => {
    fc.assert(
      fc.property(diagramEdgesArb, (edges) => {
        const result = createEdgesFromRelationships(edges);
        for (let i = 0; i < edges.length; i++) {
          expect(result[i].data.category).toBe(edges[i].category);
          expect(result[i].data.derivedFrom).toBe(edges[i].derived_from);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('empty input produces empty output', () => {
    const result = createEdgesFromRelationships([]);
    expect(result).toEqual([]);
    expect(result.length).toBe(0);
  });
});
