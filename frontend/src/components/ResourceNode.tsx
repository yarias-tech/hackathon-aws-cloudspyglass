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
 * - Displays the official AWS SVG icon at 48x48 centered above the resource name
 * - Shows the resource name and type below the icon
 * - Uses a dashed border for external components (Requirement 5.6)
 * - Falls back to a generic placeholder icon (gray square with "?") on load failure (Requirement 2.6)
 * - Shows placeholder when no icon mapping exists (Requirement 2.3)
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

  const showPlaceholder = iconError || !iconUrl;

  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div className={classNames}>
        <div className="resource-node__icon">
          {showPlaceholder ? (
            <div
              className="resource-node__icon--placeholder"
              aria-label={`${resourceType} icon placeholder`}
            >
              ?
            </div>
          ) : (
            <img
              src={iconUrl}
              alt={`${resourceType} icon`}
              width={48}
              height={48}
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
