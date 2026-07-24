import { useState, useCallback, useRef, memo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
  type Edge,
} from '@xyflow/react';
import './RelationshipEdge.css';

/** Known relationship categories */
export type RelationshipCategory = 'network' | 'iam' | 'event' | 'data';

/** Data shape passed from DiagramCanvas via the edge's `data` field */
export interface RelationshipEdgeData {
  category: string;
  derivedFrom?: string;
  label?: string | null;
  sourceName?: string;
  targetName?: string;
  [key: string]: unknown;
}

/** Edge style definition */
export interface EdgeStyleConfig {
  stroke: string;
  strokeDasharray?: string;
  animated: boolean;
}

/** Edge styling configuration per design specification (Requirements 4.2-4.5, 4.9) */
export const EDGE_STYLES: Record<RelationshipCategory, EdgeStyleConfig> = {
  network: { stroke: '#2563EB', animated: true },
  iam: { stroke: '#DC2626', strokeDasharray: '5 5', animated: true },
  event: { stroke: '#EA580C', strokeDasharray: '2 2', animated: true },
  data: { stroke: '#7C3AED', animated: true },
};

/** Default/fallback style for unknown categories (Requirement 4.9) */
export const DEFAULT_EDGE_STYLE: EdgeStyleConfig = {
  stroke: '#6B7280',
  animated: false,
};

/** Category display labels */
export const CATEGORY_LABELS: Record<string, string> = {
  network: 'Network',
  iam: 'IAM',
  event: 'Event',
  data: 'Data',
};

/** Maximum label length before truncation (Requirement 4.6) */
const MAX_LABEL_LENGTH = 40;

/**
 * Truncates a label to MAX_LABEL_LENGTH characters + ellipsis if it exceeds that length.
 * Returns the original string unmodified if length <= MAX_LABEL_LENGTH.
 * (Requirement 4.6 - Property 8: Edge Label Truncation)
 */
export function truncateLabel(label: string): string {
  if (label.length <= MAX_LABEL_LENGTH) {
    return label;
  }
  return label.slice(0, MAX_LABEL_LENGTH) + '\u2026';
}

/**
 * Returns the edge style for a given category.
 * Falls back to DEFAULT_EDGE_STYLE for unknown categories.
 */
export function getEdgeStyle(category: string): EdgeStyleConfig {
  if (Object.hasOwn(EDGE_STYLES, category)) {
    return EDGE_STYLES[category as RelationshipCategory];
  }
  return DEFAULT_EDGE_STYLE;
}

/**
 * Converts an array of DiagramEdge objects to React Flow Edge objects.
 * Maintains a 1:1 mapping — every input relationship produces exactly one output edge
 * with the same source and target, type 'relationship', and category/derivedFrom data.
 * (Property 9: Edge Count Matches Relationships — Requirement 4.1)
 */
export function createEdgesFromRelationships(
  diagramEdges: Array<{
    id: string;
    source: string;
    target: string;
    category: string;
    derived_from: string;
    label: string | null;
  }>
): Array<{
  id: string;
  source: string;
  target: string;
  type: string;
  data: { category: string; derivedFrom: string };
}> {
  return diagramEdges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'relationship',
    data: {
      category: edge.category,
      derivedFrom: edge.derived_from,
    },
  }));
}

/**
 * Extracts a short readable name from an ARN or returns the value as-is.
 * e.g., "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123" → "i-abc123"
 */
function extractResourceName(arn: string): string {
  if (!arn.startsWith('arn:')) return arn;
  const parts = arn.split(':');
  const resource = parts[parts.length - 1];
  const slashIndex = resource.indexOf('/');
  if (slashIndex !== -1) return resource.substring(slashIndex + 1);
  return resource;
}

/**
 * RelationshipEdge renders a custom edge between connected resource nodes.
 *
 * - Color-coded by category: blue solid (network), red dashed (iam),
 *   orange dotted animated (event), purple solid (data), gray solid (other)
 *   — Requirements 4.2, 4.3, 4.4, 4.5, 4.9
 * - Label truncation at 40 chars + "…" — Requirement 4.6
 * - Hover: increase stroke to 3px, show tooltip — Requirements 4.7, 4.8
 * - Edge routing around containers via getSmoothStepPath with offset/borderRadius — Requirement 4.7
 */
export const RelationshipEdge = memo(function RelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  source,
  target,
  data,
  markerEnd,
}: EdgeProps<Edge<RelationshipEdgeData>>) {
  const [isHovered, setIsHovered] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const edgeData = data as unknown as RelationshipEdgeData | undefined;
  const category = edgeData?.category ?? 'network';
  const derivedFrom = edgeData?.derivedFrom ?? '';
  const label = edgeData?.label ?? null;
  const sourceName = edgeData?.sourceName;
  const targetName = edgeData?.targetName;
  const style = getEdgeStyle(category);

  // Use getSmoothStepPath with offset and borderRadius for container-aware routing (Requirement 4.7)
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 12,
    offset: 20,
  });

  const handleMouseEnter = useCallback(
    (event: React.MouseEvent) => {
      setIsHovered(true);
      const svgRect = (
        event.currentTarget.closest('svg') as SVGSVGElement
      )?.getBoundingClientRect();
      if (svgRect) {
        setTooltipPosition({
          x: event.clientX - svgRect.left,
          y: event.clientY - svgRect.top,
        });
      }
      // Show tooltip within 200ms per Requirement 4.8
      hoverTimerRef.current = setTimeout(() => {
        setShowTooltip(true);
      }, 100);
    },
    []
  );

  const handleMouseMove = useCallback((event: React.MouseEvent) => {
    const svgRect = (
      event.currentTarget.closest('svg') as SVGSVGElement
    )?.getBoundingClientRect();
    if (svgRect) {
      setTooltipPosition({
        x: event.clientX - svgRect.left,
        y: event.clientY - svgRect.top,
      });
    }
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setShowTooltip(false);
  }, []);

  const pathClassName = [
    'relationship-edge__path--interactive',
    style.animated ? 'relationship-edge__path--animated' : '',
  ]
    .filter(Boolean)
    .join(' ');

  // Stroke width: 3px on hover, 2px default (Requirement 4.7)
  const strokeWidth = isHovered ? 3 : 2;

  // Determine tooltip content (Requirement 4.8):
  // Show derived_from if present and non-empty; otherwise show category + source/target names
  const hasDerivedFrom = derivedFrom && derivedFrom.trim().length > 0;
  const categoryLabel = CATEGORY_LABELS[category] ?? category;

  // Truncate label for display (Requirement 4.6)
  const displayLabel = label ? truncateLabel(label) : null;

  return (
    <>
      {/* Visible styled edge path */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: style.stroke,
          strokeWidth,
          strokeDasharray: style.strokeDasharray,
        }}
        className={style.animated ? 'relationship-edge__path--animated' : undefined}
      />

      {/* Invisible wider path for easier hover interaction */}
      <path
        d={edgePath}
        className={pathClassName}
        onMouseEnter={handleMouseEnter}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        data-testid={`edge-hover-${id}`}
      />

      {/* Edge label (Requirement 4.6) */}
      {displayLabel && (
        <EdgeLabelRenderer>
          <div
            className="relationship-edge__label"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'none',
            }}
            data-testid={`edge-label-${id}`}
          >
            {displayLabel}
          </div>
        </EdgeLabelRenderer>
      )}

      {/* Tooltip (Requirements 4.7, 4.8) */}
      {showTooltip && (
        <foreignObject
          x={tooltipPosition.x}
          y={tooltipPosition.y}
          width={1}
          height={1}
          overflow="visible"
          style={{ pointerEvents: 'none' }}
        >
          <div
            className="relationship-edge__tooltip"
            role="tooltip"
            aria-label={`${categoryLabel} relationship`}
            data-testid={`edge-tooltip-${id}`}
          >
            {hasDerivedFrom ? (
              <div className="relationship-edge__tooltip-row">
                <span className="relationship-edge__tooltip-label">Derived from:</span>
                <span className="relationship-edge__tooltip-value">
                  {derivedFrom}
                </span>
              </div>
            ) : (
              <>
                <div className="relationship-edge__tooltip-row">
                  <span className="relationship-edge__tooltip-label">Type:</span>
                  <span className="relationship-edge__tooltip-value">
                    {categoryLabel}
                  </span>
                </div>
                <div className="relationship-edge__tooltip-row">
                  <span className="relationship-edge__tooltip-label">Source:</span>
                  <span className="relationship-edge__tooltip-value" title={source}>
                    {sourceName ?? extractResourceName(source)}
                  </span>
                </div>
                <div className="relationship-edge__tooltip-row">
                  <span className="relationship-edge__tooltip-label">Target:</span>
                  <span className="relationship-edge__tooltip-value" title={target}>
                    {targetName ?? extractResourceName(target)}
                  </span>
                </div>
              </>
            )}
          </div>
        </foreignObject>
      )}
    </>
  );
});
