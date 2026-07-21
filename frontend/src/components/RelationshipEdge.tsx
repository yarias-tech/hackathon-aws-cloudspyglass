import { useState, useCallback, useRef, memo } from 'react';
import {
  BaseEdge,
  getSmoothStepPath,
  type EdgeProps,
  type Edge,
} from '@xyflow/react';
import './RelationshipEdge.css';

/** Data shape passed from DiagramCanvas via the edge's `data` field */
export interface RelationshipEdgeData {
  category: 'network' | 'iam' | 'event' | 'data';
  derivedFrom: string;
  [key: string]: unknown;
}

/** Edge styling configuration per design specification (Requirement 5.3) */
const EDGE_STYLES: Record<
  RelationshipEdgeData['category'],
  { stroke: string; strokeDasharray?: string; animated: boolean }
> = {
  network: { stroke: '#2563eb', animated: false },
  iam: { stroke: '#16a34a', strokeDasharray: '5 5', animated: false },
  event: { stroke: '#ea580c', strokeDasharray: '3 3', animated: true },
  data: { stroke: '#6b7280', animated: false },
};

/** Category display labels */
const CATEGORY_LABELS: Record<RelationshipEdgeData['category'], string> = {
  network: 'Network',
  iam: 'IAM',
  event: 'Event',
  data: 'Data',
};

/**
 * Extracts a short readable name from an ARN or returns the value as-is.
 * e.g., "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123" → "i-abc123"
 */
function extractResourceName(arn: string): string {
  if (!arn.startsWith('arn:')) return arn;
  const parts = arn.split(':');
  const resource = parts[parts.length - 1];
  // Handle resource types like "instance/i-abc123" or "function:my-function"
  const slashIndex = resource.indexOf('/');
  if (slashIndex !== -1) return resource.substring(slashIndex + 1);
  return resource;
}

/**
 * RelationshipEdge renders a custom edge between connected resource nodes.
 *
 * - Color-coded by category: blue (network), green dashed (iam),
 *   orange dotted animated (event), gray (data) — Requirement 5.3
 * - Tooltip on hover (within 200ms) showing interaction type, source,
 *   target, and derived_from — Requirement 5.8
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
  const [showTooltip, setShowTooltip] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const edgeData = data as unknown as RelationshipEdgeData | undefined;
  const category = edgeData?.category ?? 'network';
  const derivedFrom = edgeData?.derivedFrom ?? '';
  const style = EDGE_STYLES[category];

  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });

  const handleMouseEnter = useCallback(
    (event: React.MouseEvent) => {
      const svgRect = (
        event.currentTarget.closest('svg') as SVGSVGElement
      )?.getBoundingClientRect();
      if (svgRect) {
        setTooltipPosition({
          x: event.clientX - svgRect.left,
          y: event.clientY - svgRect.top,
        });
      }
      // Show tooltip within 200ms per Requirement 5.8
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

  return (
    <>
      {/* Visible styled edge path */}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: style.stroke,
          strokeWidth: 2,
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

      {/* Tooltip (Requirement 5.8) */}
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
            aria-label={`${CATEGORY_LABELS[category]} relationship`}
            data-testid={`edge-tooltip-${id}`}
          >
            <div className="relationship-edge__tooltip-row">
              <span className="relationship-edge__tooltip-label">Type:</span>
              <span className="relationship-edge__tooltip-value">
                {CATEGORY_LABELS[category]}
              </span>
            </div>
            <div className="relationship-edge__tooltip-row">
              <span className="relationship-edge__tooltip-label">Source:</span>
              <span className="relationship-edge__tooltip-value" title={source}>
                {extractResourceName(source)}
              </span>
            </div>
            <div className="relationship-edge__tooltip-row">
              <span className="relationship-edge__tooltip-label">Target:</span>
              <span className="relationship-edge__tooltip-value" title={target}>
                {extractResourceName(target)}
              </span>
            </div>
            <div className="relationship-edge__tooltip-row">
              <span className="relationship-edge__tooltip-label">Derived from:</span>
              <span className="relationship-edge__tooltip-value">
                {derivedFrom}
              </span>
            </div>
          </div>
        </foreignObject>
      )}
    </>
  );
});

/** Export the edge styles map for use in tests */
export { EDGE_STYLES, CATEGORY_LABELS };
