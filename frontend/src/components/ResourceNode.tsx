import { useState, useCallback, memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import './ResourceNode.css';

/** Data shape passed from DiagramCanvas via the node's `data` field */
export interface ResourceNodeData {
  label: string;
  resourceType: string;
  region: string;
  isExternal: boolean;
  isUnresolved: boolean;
  iconUrl: string;
  [key: string]: unknown;
}

/**
 * ResourceNode renders an AWS resource as a custom React Flow node.
 *
 * - Displays the official AWS SVG icon loaded from /api/images/icons/{service_type}
 * - Shows the resource name and type
 * - Uses a dashed border for external components (Requirement 5.6)
 * - Falls back to a placeholder icon on load failure (Requirement 5.9)
 */
export const ResourceNode = memo(function ResourceNode({
  data,
}: NodeProps) {
  const { label, resourceType, isExternal, isUnresolved, iconUrl } =
    data as unknown as ResourceNodeData;

  const [iconError, setIconError] = useState(false);

  const handleIconError = useCallback(() => {
    setIconError(true);
  }, []);

  const classNames = [
    'resource-node',
    isExternal ? 'resource-node--external' : '',
    isUnresolved ? 'resource-node--unresolved' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div className={classNames}>
        <div className="resource-node__icon">
          {iconError ? (
            <div
              className="resource-node__icon--placeholder"
              aria-label={`${resourceType} icon placeholder`}
            >
              ☁
            </div>
          ) : (
            <img
              src={iconUrl}
              alt={`${resourceType} icon`}
              onError={handleIconError}
            />
          )}
        </div>
        <div className="resource-node__info">
          <span className="resource-node__name" title={label}>
            {label}
          </span>
          <span className="resource-node__type">{resourceType}</span>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
});
