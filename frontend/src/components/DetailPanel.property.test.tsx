import { describe, it, expect, vi } from 'vitest';
import * as fc from 'fast-check';
import { render, cleanup } from '@testing-library/react';
import { DetailPanel } from './DetailPanel';
import type { Resource } from '../types/resources';

/**
 * **Validates: Requirements 6.1**
 *
 * Property 13: Detail panel metadata completeness
 * For any resource of a given type, when selected, the Detail_Panel SHALL display
 * all metadata fields applicable to that resource type (ARN, region, tags,
 * creation_date, iam_role, type-specific attributes) and SHALL omit sections
 * for fields not applicable to the resource type.
 */
describe('Property 13: Detail panel metadata completeness', () => {
  /** Arbitrary for generating valid Resource objects */
  const resourceArb: fc.Arbitrary<Resource> = fc.record({
    arn: fc.stringMatching(/^arn:aws:[a-z0-9]+:[a-z0-9-]*:\d{12}:[a-z0-9/:-]+$/),
    resource_type: fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789'.split('')), { minLength: 2, maxLength: 15 }),
    name: fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789-_'.split('')), { minLength: 1, maxLength: 30 }),
    region: fc.constantFrom('us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'),
    tags: fc.dictionary(
      fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789'.split('')), { minLength: 1, maxLength: 20 }),
      fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789'.split('')), { minLength: 1, maxLength: 30 }),
      { minKeys: 0, maxKeys: 5 }
    ),
    creation_date: fc.oneof(
      fc.constant(null),
      fc.date({ min: new Date('2020-01-01'), max: new Date('2025-01-01') }).map(d => d.toISOString())
    ),
    iam_role: fc.oneof(
      fc.constant(null),
      fc.stringMatching(/^arn:aws:iam::\d{12}:role\/[A-Za-z0-9]+$/)
    ),
    attributes: fc.dictionary(
      fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz_'.split('')), { minLength: 1, maxLength: 20 }),
      fc.oneof(fc.string({ minLength: 1, maxLength: 20 }), fc.integer(), fc.boolean()) as fc.Arbitrary<unknown>,
      { minKeys: 0, maxKeys: 5 }
    ),
    is_external: fc.boolean(),
    is_unresolved: fc.boolean(),
  });

  /**
   * Helper: query section headings to determine which sections are rendered.
   * This avoids collisions from getByText when generated field values overlap.
   */
  function getSectionTitles(container: HTMLElement): string[] {
    const headings = container.querySelectorAll('.detail-panel__section-title');
    return Array.from(headings).map(el => el.textContent ?? '');
  }

  /** Helper: get field values within the Identifiers section */
  function getIdentifierFields(container: HTMLElement) {
    const sections = container.querySelectorAll('.detail-panel__section');
    const identifiersSection = Array.from(sections).find(
      section => section.querySelector('.detail-panel__section-title')?.textContent === 'Identifiers'
    );
    if (!identifiersSection) return { arn: null, region: null, name: null };

    const fields = identifiersSection.querySelectorAll('.detail-panel__field');
    const result: Record<string, string | null> = { arn: null, region: null, name: null };

    fields.forEach(field => {
      const label = field.querySelector('.detail-panel__label')?.textContent;
      const value = field.querySelector('.detail-panel__value')?.textContent;
      if (label === 'ARN') result.arn = value ?? null;
      if (label === 'Region') result.region = value ?? null;
      if (label === 'Name') result.name = value ?? null;
    });

    return result;
  }

  it('always displays Identifiers section (ARN, Region, Name) for any resource', () => {
    fc.assert(
      fc.property(resourceArb, (resource) => {
        cleanup();
        const { container } = render(
          <DetailPanel resource={resource} onClose={vi.fn()} />
        );

        const sections = getSectionTitles(container);
        expect(sections).toContain('Identifiers');

        const identifiers = getIdentifierFields(container);
        expect(identifiers.arn).toBe(resource.arn);
        expect(identifiers.region).toBe(resource.region);
        expect(identifiers.name).toBe(resource.name);
      }),
      { numRuns: 50 }
    );
  });

  it('shows Tags section IFF resource.tags has at least one entry', () => {
    fc.assert(
      fc.property(resourceArb, (resource) => {
        cleanup();
        const { container } = render(
          <DetailPanel resource={resource} onClose={vi.fn()} />
        );

        const sections = getSectionTitles(container);
        const hasTags = Object.keys(resource.tags).length > 0;

        if (hasTags) {
          expect(sections).toContain('Tags');
          // Verify each tag key appears in a tag-key element
          const tagKeyElements = container.querySelectorAll('.detail-panel__tag-key');
          const renderedKeys = Array.from(tagKeyElements).map(el => el.textContent);
          for (const key of Object.keys(resource.tags)) {
            expect(renderedKeys).toContain(key);
          }
        } else {
          expect(sections).not.toContain('Tags');
        }
      }),
      { numRuns: 50 }
    );
  });

  it('shows IAM Role section IFF resource.iam_role is non-null', () => {
    fc.assert(
      fc.property(resourceArb, (resource) => {
        cleanup();
        const { container } = render(
          <DetailPanel resource={resource} onClose={vi.fn()} />
        );

        const sections = getSectionTitles(container);

        if (resource.iam_role) {
          expect(sections).toContain('IAM Role');
          // Find the IAM Role section and verify value
          const allSections = container.querySelectorAll('.detail-panel__section');
          const iamSection = Array.from(allSections).find(
            s => s.querySelector('.detail-panel__section-title')?.textContent === 'IAM Role'
          );
          const value = iamSection?.querySelector('.detail-panel__value')?.textContent;
          expect(value).toBe(resource.iam_role);
        } else {
          expect(sections).not.toContain('IAM Role');
        }
      }),
      { numRuns: 50 }
    );
  });

  it('shows Creation Date section IFF resource.creation_date is non-null', () => {
    fc.assert(
      fc.property(resourceArb, (resource) => {
        cleanup();
        const { container } = render(
          <DetailPanel resource={resource} onClose={vi.fn()} />
        );

        const sections = getSectionTitles(container);

        if (resource.creation_date) {
          expect(sections).toContain('Creation Date');
          // Find the Creation Date section and verify value
          const allSections = container.querySelectorAll('.detail-panel__section');
          const dateSection = Array.from(allSections).find(
            s => s.querySelector('.detail-panel__section-title')?.textContent === 'Creation Date'
          );
          const value = dateSection?.querySelector('.detail-panel__value')?.textContent;
          expect(value).toBe(resource.creation_date);
        } else {
          expect(sections).not.toContain('Creation Date');
        }
      }),
      { numRuns: 50 }
    );
  });

  it('shows Attributes section IFF resource.attributes has at least one entry', () => {
    fc.assert(
      fc.property(resourceArb, (resource) => {
        cleanup();
        const { container } = render(
          <DetailPanel resource={resource} onClose={vi.fn()} />
        );

        const sections = getSectionTitles(container);
        const hasAttributes = Object.keys(resource.attributes).length > 0;

        if (hasAttributes) {
          expect(sections).toContain('Attributes');
          // Verify each attribute key appears
          const attrKeyElements = container.querySelectorAll('.detail-panel__attribute-key');
          const renderedKeys = Array.from(attrKeyElements).map(el => el.textContent);
          for (const key of Object.keys(resource.attributes)) {
            expect(renderedKeys).toContain(key);
          }
        } else {
          expect(sections).not.toContain('Attributes');
        }
      }),
      { numRuns: 50 }
    );
  });
});
