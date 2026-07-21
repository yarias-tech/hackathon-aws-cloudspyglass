import { describe, it, expect } from 'vitest';
import { EDGE_STYLES, CATEGORY_LABELS } from './RelationshipEdge';

describe('RelationshipEdge', () => {
  describe('Edge styling by category (Requirement 5.3)', () => {
    it('network category uses blue solid styling', () => {
      const style = EDGE_STYLES.network;
      expect(style.stroke).toBe('#2563eb');
      expect(style.strokeDasharray).toBeUndefined();
      expect(style.animated).toBe(false);
    });

    it('iam category uses green dashed styling', () => {
      const style = EDGE_STYLES.iam;
      expect(style.stroke).toBe('#16a34a');
      expect(style.strokeDasharray).toBeDefined();
      expect(style.animated).toBe(false);
    });

    it('event category uses orange dotted animated styling', () => {
      const style = EDGE_STYLES.event;
      expect(style.stroke).toBe('#ea580c');
      expect(style.strokeDasharray).toBeDefined();
      expect(style.animated).toBe(true);
    });

    it('data category uses gray solid styling', () => {
      const style = EDGE_STYLES.data;
      expect(style.stroke).toBe('#6b7280');
      expect(style.strokeDasharray).toBeUndefined();
      expect(style.animated).toBe(false);
    });

    it('all four categories have defined styles', () => {
      const categories: Array<keyof typeof EDGE_STYLES> = ['network', 'iam', 'event', 'data'];
      for (const category of categories) {
        expect(EDGE_STYLES[category]).toBeDefined();
        expect(EDGE_STYLES[category].stroke).toBeTruthy();
        expect(typeof EDGE_STYLES[category].animated).toBe('boolean');
      }
    });
  });

  describe('Category labels', () => {
    it('provides human-readable labels for all categories', () => {
      expect(CATEGORY_LABELS.network).toBe('Network');
      expect(CATEGORY_LABELS.iam).toBe('IAM');
      expect(CATEGORY_LABELS.event).toBe('Event');
      expect(CATEGORY_LABELS.data).toBe('Data');
    });
  });

  describe('Edge style differentiation', () => {
    it('network and data have no dash array (solid lines)', () => {
      expect(EDGE_STYLES.network.strokeDasharray).toBeUndefined();
      expect(EDGE_STYLES.data.strokeDasharray).toBeUndefined();
    });

    it('iam and event have dash arrays (non-solid lines)', () => {
      expect(EDGE_STYLES.iam.strokeDasharray).toBeDefined();
      expect(EDGE_STYLES.event.strokeDasharray).toBeDefined();
    });

    it('only event category is animated', () => {
      expect(EDGE_STYLES.network.animated).toBe(false);
      expect(EDGE_STYLES.iam.animated).toBe(false);
      expect(EDGE_STYLES.event.animated).toBe(true);
      expect(EDGE_STYLES.data.animated).toBe(false);
    });

    it('all categories have distinct colors', () => {
      const colors = Object.values(EDGE_STYLES).map((s) => s.stroke);
      const uniqueColors = new Set(colors);
      expect(uniqueColors.size).toBe(4);
    });
  });
});
