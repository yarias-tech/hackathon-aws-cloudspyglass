import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { EDGE_STYLES } from './RelationshipEdge';

/**
 * **Validates: Requirements 5.3**
 *
 * Property 12: Edge styling by category
 * For any relationship category, the Diagram_Renderer SHALL apply the correct
 * visual style: blue solid for network, green dashed for iam, orange dotted
 * animated for event, and gray solid for data.
 */
describe('Property 12: Edge styling by category', () => {
  /** Expected styling per the design specification */
  const EXPECTED_STYLES: Record<
    string,
    { stroke: string; hasDashArray: boolean; animated: boolean }
  > = {
    network: { stroke: '#2563eb', hasDashArray: false, animated: false },
    iam: { stroke: '#16a34a', hasDashArray: true, animated: false },
    event: { stroke: '#ea580c', hasDashArray: true, animated: true },
    data: { stroke: '#6b7280', hasDashArray: false, animated: false },
  };

  const categoryArb = fc.constantFrom(
    'network' as const,
    'iam' as const,
    'event' as const,
    'data' as const
  );

  it('each category maps to the correct color, dash style, and animation', () => {
    fc.assert(
      fc.property(categoryArb, (category) => {
        const style = EDGE_STYLES[category];
        const expected = EXPECTED_STYLES[category];

        // Correct color
        expect(style.stroke).toBe(expected.stroke);

        // Correct dash array presence
        if (expected.hasDashArray) {
          expect(style.strokeDasharray).toBeDefined();
        } else {
          expect(style.strokeDasharray).toBeUndefined();
        }

        // Correct animation flag
        expect(style.animated).toBe(expected.animated);
      }),
      { numRuns: 100 }
    );
  });

  it('all categories have distinct colors (no two categories share a color)', () => {
    fc.assert(
      fc.property(
        categoryArb,
        categoryArb,
        (catA, catB) => {
          if (catA !== catB) {
            expect(EDGE_STYLES[catA].stroke).not.toBe(EDGE_STYLES[catB].stroke);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('only event category has animation enabled', () => {
    fc.assert(
      fc.property(categoryArb, (category) => {
        if (category === 'event') {
          expect(EDGE_STYLES[category].animated).toBe(true);
        } else {
          expect(EDGE_STYLES[category].animated).toBe(false);
        }
      }),
      { numRuns: 100 }
    );
  });

  it('solid categories have no strokeDasharray and non-solid categories have strokeDasharray defined', () => {
    const solidCategories = ['network', 'data'] as const;
    const nonSolidCategories = ['iam', 'event'] as const;

    fc.assert(
      fc.property(fc.constantFrom(...solidCategories), (category) => {
        expect(EDGE_STYLES[category].strokeDasharray).toBeUndefined();
      }),
      { numRuns: 50 }
    );

    fc.assert(
      fc.property(fc.constantFrom(...nonSolidCategories), (category) => {
        expect(EDGE_STYLES[category].strokeDasharray).toBeDefined();
      }),
      { numRuns: 50 }
    );
  });

  it('EDGE_STYLES covers exactly the 4 required categories (no more, no less)', () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const requiredCategories = new Set(['network', 'iam', 'event', 'data']);
        const actualCategories = new Set(Object.keys(EDGE_STYLES));

        // No missing categories
        for (const required of requiredCategories) {
          expect(actualCategories.has(required)).toBe(true);
        }

        // No extra categories
        for (const actual of actualCategories) {
          expect(requiredCategories.has(actual)).toBe(true);
        }

        // Exactly 4
        expect(actualCategories.size).toBe(4);
      }),
      { numRuns: 1 }
    );
  });
});
