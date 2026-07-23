import { useState, useCallback, memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import './ContainerNode.css';

/** Data shape for container nodes, passed via the node's `data` field */
export interface ContainerNodeData {
  label: string;
  containerType: 'cloud' | 'account' | 'region' | 'vpc' | 'az' | 'subnet';
  subnetType?: 'public' | 'private';
  iconUrl: string;
  isCollapsed: boolean;
  resourceCount: number;
  /** Callback from DiagramCanvas to toggle collapse state centrally (Requirement 8.9) */
  onToggleCollapse?: (containerId: string) => void;
  [key: string]: unknown;
}

/**
 * Returns the CSS modifier class for the container type.
 * Subnet containers differentiate by subnetType (public/private).
 */
function getContainerStyleClass(
  containerType: ContainerNodeData['containerType'],
  subnetType?: ContainerNodeData['subnetType']
): string {
  if (containerType === 'subnet') {
    return subnetType === 'public'
      ? 'container-node--subnet-public'
      : 'container-node--subnet-private';
  }
  return `container-node--${containerType}`;
}

/**
 * ContainerNode renders an AWS infrastructure container as a custom React Flow group node.
 *
 * - Styled per container type (cloud, account, region, vpc, az, subnet)
 * - Displays a header bar with 32x32 icon badge and 14px/600-weight label
 * - Supports collapsed state: shows only header + resource count badge
 * - Double-click toggles collapse/expand (Requirement 8.3)
 * - Resource count badge shows total recursive resource count (Requirement 8.4)
 * - Collapse state is managed by parent DiagramCanvas for edge rerouting (Requirement 8.9)
 */
export const ContainerNode = memo(function ContainerNode({ id, data }: NodeProps) {
  const {
    label,
    containerType,
    subnetType,
    iconUrl,
    isCollapsed,
    resourceCount,
    onToggleCollapse,
  } = data as unknown as ContainerNodeData;

  const [iconError, setIconError] = useState(false);

  const handleDoubleClick = useCallback(() => {
    if (onToggleCollapse) {
      // Delegate collapse to parent DiagramCanvas (centralized state for edge rerouting)
      onToggleCollapse(id);
    }
  }, [onToggleCollapse, id]);

  const handleIconError = useCallback(() => {
    setIconError(true);
  }, []);

  const styleClass = getContainerStyleClass(containerType, subnetType);

  const classNames = [
    'container-node',
    styleClass,
    isCollapsed ? 'container-node--collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div
        className={classNames}
        onDoubleClick={handleDoubleClick}
        data-testid="container-node"
      >
        <div className="container-node__header">
          <div className="container-node__icon">
            {iconError || !iconUrl ? (
              <div
                className="container-node__icon--placeholder"
                aria-label={`${containerType} icon placeholder`}
              >
                ☁
              </div>
            ) : (
              <img
                src={iconUrl}
                alt={`${containerType} group icon`}
                onError={handleIconError}
              />
            )}
          </div>
          <span className="container-node__label">{label}</span>
          {isCollapsed && (
            <span className="container-node__badge" aria-label="resource count">
              {resourceCount}
            </span>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
});
