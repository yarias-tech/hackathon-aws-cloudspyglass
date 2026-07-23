import { describe, it, expect } from 'vitest';
import {
  EDGE_STYLES,
  CATEGORY_LABELS,
  DEFAULT_EDGE_STYLE,
  truncateLabel,
  getEdgeStyle,
} from './RelationshipEdge';

describe('RelationshipEdge', () => {
  describe('Edge styling by category (Requirements 4.2-4.5, 4.9)', () => {
    it('network category uses blue solid styling', () => {
      const style = EDGE_STYLES.network;
      expect(style.stroke).toBe('#2563EB');
      expect(style.strokeDasharray).toBeUndefined();
      expect(style.animated).toBe(false);
    });

    it('iam category uses red dashed styling', () => {
      const style = EDGE_STYLES.iam;
      expect(style.stroke).toBe('#DC2626');
      expect(style.strokeDasharray).toBe('5 5');
      expect(style.animated).toBe(false);
    });

    it('event category uses orange dotted animated styling', () => {
      const style = EDGE_STYLES.event;
      expect(style.stroke).toBe('#EA580C');
      expect(style.strokeDasharray).toBe('2 2');
      expect(style.animated).toBe(true);
    });

    it('data category uses purple solid styling', () => {
      const style = EDGE_STYLES.data;
      expect(style.stroke).toBe('#7C3AED');
      expect(style.strokeDasharray).toBeUndefined();
      expect(style.animated).toBe(false);
    });

    it('unknown/other category falls back to gray solid styling', () => {
      const style = getEdgeStyle('unknown');
      expect(style.stroke).toBe('#6B7280');
      expect(style.strokeDasharray).toBeUndefined();
      expect(style.animated).toBe(false);
    });

    it('DEFAULT_EDGE_STYLE is gray solid', () => {
      expect(DEFAULT_EDGE_STYLE.stroke).toBe('#6B7280');
      expect(DEFAULT_EDGE_STYLE.strokeDasharray).toBeUndefined();
      expect(DEFAULT_EDGE_STYLE.animated).toBe(false);
    });

    it('all four known categories have defined styles', () => {
      const categories: Array<keyof typeof EDGE_STYLES> = ['network', 'iam', 'event', 'data'];
      for (const category of categories) {
        expect(EDGE_STYLES[category]).toBeDefined();
        expect(EDGE_STYLES[category].stroke).toBeTruthy();
        expect(typeof EDGE_STYLES[category].animated).toBe('boolean');
      }
    });
  });

  describe('getEdgeStyle helper', () => {
    it('returns the correct style for known categories', () => {
      expect(getEdgeStyle('network')).toBe(EDGE_STYLES.network);
      expect(getEdgeStyle('iam')).toBe(EDGE_STYLES.iam);
      expect(getEdgeStyle('event')).toBe(EDGE_STYLES.event);
      expect(getEdgeStyle('data')).toBe(EDGE_STYLES.data);
    });

    it('returns DEFAULT_EDGE_STYLE for unknown categories', () => {
      expect(getEdgeStyle('unknown')).toBe(DEFAULT_EDGE_STYLE);
      expect(getEdgeStyle('other')).toBe(DEFAULT_EDGE_STYLE);
      expect(getEdgeStyle('custom-category')).toBe(DEFAULT_EDGE_STYLE);
      expect(getEdgeStyle('')).toBe(DEFAULT_EDGE_STYLE);
    });
  });

  describe('Category labels', () => {
    it('provides human-readable labels for known categories', () => {
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
      expect(EDGE_STYLES.iam.strokeDasharray).toBe('5 5');
      expect(EDGE_STYLES.event.strokeDasharray).toBe('2 2');
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

  describe('Label truncation (Requirement 4.6)', () => {
    it('returns short labels unmodified', () => {
      expect(truncateLabel('hello')).toBe('hello');
      expect(truncateLabel('')).toBe('');
    });

    it('returns labels of exactly 40 chars unmodified', () => {
      const label40 = 'a'.repeat(40);
      expect(truncateLabel(label40)).toBe(label40);
    });

    it('truncates labels longer than 40 chars with ellipsis', () => {
      const label41 = 'a'.repeat(41);
      expect(truncateLabel(label41)).toBe('a'.repeat(40) + '\u2026');
      expect(truncateLabel(label41).length).toBe(41);
    });

    it('truncates very long labels', () => {
      const label200 = 'x'.repeat(200);
      expect(truncateLabel(label200)).toBe('x'.repeat(40) + '\u2026');
    });
  });
});
