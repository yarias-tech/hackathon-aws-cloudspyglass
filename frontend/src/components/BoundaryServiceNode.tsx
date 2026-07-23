import { useState, useCallback, memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import './BoundaryServiceNode.css';

/** Data shape for boundary service nodes, passed via the node's `data` field */
export interface BoundaryServiceNodeData {
  label: string;
  resourceType: string;
  iconUrl: string;
  boundaryType: 'igw' | 'nat' | 'waf' | 'vpn';
  [key: string]: unknown;
}

/**
 * BoundaryServiceNode renders an AWS boundary service (Internet Gateway, NAT Gateway,
 * WAF, VPN Gateway) as a custom React Flow node.
 *
 * - Displays a 48x48 resource icon centered above the label
 * - Styled per boundary type with color-coded borders and backgrounds
 * - Visual cue (straddling indicator bar) indicates boundary positioning
 * - Falls back to a placeholder icon on load error
 * - Positioned at container edges (50% inside, 50% outside) by the layout engine
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
 */
export const BoundaryServiceNode = memo(function BoundaryServiceNode({ data }: NodeProps) {
  const { label, iconUrl, boundaryType } = data as unknown as BoundaryServiceNodeData;

  const [iconError, setIconError] = useState(false);

  const handleIconError = useCallback(() => {
    setIconError(true);
  }, []);

  const classNames = [
    'boundary-service-node',
    `boundary-service-node--${boundaryType}`,
  ].join(' ');

  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div className={classNames} data-testid="boundary-service-node">
        <div className="boundary-service-node__icon">
          {iconError || !iconUrl ? (
            <div
              className="boundary-service-node__icon--placeholder"
              aria-label={`${boundaryType} icon placeholder`}
            >
              ?
            </div>
          ) : (
            <img
              src={iconUrl}
              alt={`${boundaryType} service icon`}
              onError={handleIconError}
            />
          )}
        </div>
        <span className="boundary-service-node__label">{label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
});
