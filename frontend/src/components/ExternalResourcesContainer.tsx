import { useState, useCallback, memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { DiagramNode } from '../types/diagram';
import './ExternalResourcesContainer.css';

/** Category for external resource sub-grouping */
export type ExternalCategory = 'cross_account' | 'on_premises' | 'third_party' | 'unknown';

/** A group of external resources sharing the same category */
export interface ExternalGroup {
  category: ExternalCategory;
  resources: DiagramNode[];
}

/** Data shape for the ExternalResourcesContainer node, passed via the node's `data` field */
export interface ExternalResourcesContainerData {
  label: string;
  groups: ExternalGroup[];
  [key: string]: unknown;
}

/** Human-friendly display labels for each external category */
const CATEGORY_LABELS: Record<ExternalCategory, string> = {
  cross_account: 'Cross-Account AWS',
  on_premises: 'On-Premises',
  third_party: 'Third-Party',
  unknown: 'Unknown External',
};

/** Order for rendering sub-groups (consistent visual ordering) */
const CATEGORY_ORDER: ExternalCategory[] = [
  'cross_account',
  'on_premises',
  'third_party',
  'unknown',
];

/**
 * ExternalResourceNode renders a single external resource inside a sub-group.
 * Styled with 50% opacity and dashed border per Requirement 9.4.
 */
const ExternalResourceNode = memo(function ExternalResourceNode({
  resource,
}: {
  resource: DiagramNode;
}) {
  const [iconError, setIconError] = useState(false);

  const handleIconError = useCallback(() => {
    setIconError(true);
  }, []);

  return (
    <div
      className="external-resources-container__resource-node"
      data-testid="external-resource-node"
      title={resource.name}
    >
      <div className="external-resources-container__resource-icon">
        {iconError || !resource.icon_url ? (
          <div
            className="external-resources-container__resource-icon--placeholder"
            aria-label={`${resource.resource_type} icon placeholder`}
          >
            ?
          </div>
        ) : (
          <img
            src={resource.icon_url}
            alt={`${resource.resource_type} icon`}
            onError={handleIconError}
          />
        )}
      </div>
      <span className="external-resources-container__resource-label">
        {resource.name}
      </span>
    </div>
  );
});

/**
 * ExternalResourcesContainer renders a dedicated area for external resources,
 * sub-grouped by inferred category: Cross-Account AWS, On-Premises, Third-Party,
 * and Unknown External.
 *
 * - Positioned to the right/above the AWS Cloud container (handled by layout engine)
 * - Sub-groups are rendered in consistent order with styled headers
 * - External resource nodes are styled with 50% opacity and dashed border
 * - Acts as a React Flow group node with handles for edge connections
 *
 * Requirements: 9.1, 9.2, 9.4, 9.5
 */
export const ExternalResourcesContainer = memo(function ExternalResourcesContainer({
  data,
}: NodeProps) {
  const { label, groups } = data as unknown as ExternalResourcesContainerData;

  // Sort groups by the defined category order, filtering out empty groups
  const sortedGroups = CATEGORY_ORDER
    .map((category) => groups.find((g) => g.category === category))
    .filter(
      (group): group is ExternalGroup =>
        group !== undefined && group.resources.length > 0
    );

  return (
    <>
      <Handle type="target" position={Position.Left} />
      <div
        className="external-resources-container"
        data-testid="external-resources-container"
      >
        <div className="external-resources-container__header">
          <span className="external-resources-container__title">
            {label || 'External Resources'}
          </span>
        </div>

        <div className="external-resources-container__groups">
          {sortedGroups.map((group) => (
            <div
              key={group.category}
              className={`external-resources-container__group external-resources-container__group--${group.category}`}
              data-testid={`external-group-${group.category}`}
            >
              <div className="external-resources-container__group-header">
                {CATEGORY_LABELS[group.category]}
              </div>
              <div className="external-resources-container__resources">
                {group.resources.map((resource) => (
                  <ExternalResourceNode
                    key={resource.id}
                    resource={resource}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </>
  );
});
