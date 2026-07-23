import { useCallback, useState } from 'react';
import type { DiagramData } from '../types/diagram';
import type { FilterCriteria, TagFilter } from '../types/filters';
import { TagFilterInput } from './TagFilterInput';
import { TypeFilterSelect } from './TypeFilterSelect';

interface FilterBarProps {
  /** Current diagram data (used to extract available types) */
  diagramData: DiagramData | null;
  /** Current filter criteria */
  filters: FilterCriteria;
  /** Callback when filters change */
  onFiltersChange: (filters: FilterCriteria) => void;
  /** Filtered count of resources (when filters are active) */
  filteredCount: number | null;
  /** Total count of resources */
  totalCount: number;
}

/** Reusable collapsible section header */
function SectionHeader({
  label,
  collapsed,
  onToggle,
  badge,
}: {
  label: string;
  collapsed: boolean;
  onToggle: () => void;
  badge?: number;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
        padding: '0.4rem 0',
        cursor: 'pointer',
        userSelect: 'none',
      }}
      onClick={onToggle}
      role="button"
      tabIndex={0}
      aria-expanded={!collapsed}
      aria-label={collapsed ? `Expand ${label}` : `Collapse ${label}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151' }}>
        {label}
      </span>
      <span
        style={{
          display: 'inline-block',
          fontSize: '0.6rem',
          transition: 'transform 0.2s ease',
          transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
          color: '#6b7280',
        }}
      >
        ▼
      </span>
      {collapsed && badge !== undefined && badge > 0 && (
        <span
          style={{
            fontSize: '0.6rem',
            backgroundColor: '#2563eb',
            color: '#fff',
            borderRadius: '9999px',
            padding: '0.05rem 0.35rem',
            fontWeight: 600,
          }}
        >
          {badge}
        </span>
      )}
    </div>
  );
}

/**
 * FilterBar orchestrates tag and resource-type filter controls.
 *
 * - Two independently collapsible sections: Tag Filters and Resource Types
 * - Provides AND/OR operator toggle for tag filters
 * - Displays filtered count vs total count when filters are active (Requirement 7.4)
 * - Shows empty state message when no resources match filters (Requirement 7.5)
 * - Exposes combined FilterCriteria to parent component
 */
export function FilterBar({
  diagramData,
  filters,
  onFiltersChange,
  filteredCount,
  totalCount,
}: FilterBarProps) {
  const [tagsCollapsed, setTagsCollapsed] = useState(false);
  const [typesCollapsed, setTypesCollapsed] = useState(false);

  const handleTagFiltersChange = useCallback(
    (tagFilters: TagFilter[]) => {
      onFiltersChange({
        ...filters,
        tag_filters: tagFilters,
      });
    },
    [filters, onFiltersChange]
  );

  const handleTypeFiltersChange = useCallback(
    (typeFilters: string[]) => {
      onFiltersChange({
        ...filters,
        type_filters: typeFilters,
      });
    },
    [filters, onFiltersChange]
  );

  const handleOperatorToggle = useCallback(() => {
    onFiltersChange({
      ...filters,
      tag_filter_operator: filters.tag_filter_operator === 'AND' ? 'OR' : 'AND',
    });
  }, [filters, onFiltersChange]);

  const hasActiveFilters =
    filters.tag_filters.length > 0 || filters.type_filters.length > 0;

  const handleClearAll = useCallback(() => {
    onFiltersChange({ tag_filters: [], type_filters: [], tag_filter_operator: 'AND' });
  }, [onFiltersChange]);

  return (
    <div
      className="filter-bar"
      style={{
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#fafafa',
        padding: '0.5rem 0.75rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.25rem',
      }}
    >
      {/* Top bar with count and clear */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {hasActiveFilters && filteredCount !== null && (
            <span
              aria-label="Filter results count"
              style={{ fontSize: '0.75rem', color: '#4b5563' }}
            >
              <strong>{filteredCount}</strong> of <strong>{totalCount}</strong> resources
            </span>
          )}
          {hasActiveFilters && (
            <button
              onClick={handleClearAll}
              aria-label="Clear all filters"
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.7rem',
                color: '#dc2626',
                padding: '0.125rem 0.375rem',
                borderRadius: '0.25rem',
              }}
            >
              Clear All
            </button>
          )}
        </div>
      </div>

      {/* --- Tag Filters section --- */}
      <SectionHeader
        label="Tag Filters"
        collapsed={tagsCollapsed}
        onToggle={() => setTagsCollapsed((p) => !p)}
        badge={filters.tag_filters.length}
      />
      {!tagsCollapsed && (
        <div style={{ paddingLeft: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <TagFilterInput
            filters={filters.tag_filters}
            onFiltersChange={handleTagFiltersChange}
          />
          {filters.tag_filters.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.7rem', color: '#6b7280' }}>Tag logic:</span>
              <button
                type="button"
                onClick={handleOperatorToggle}
                aria-label={`Tag filter operator: ${filters.tag_filter_operator}. Click to switch.`}
                style={{
                  padding: '0.2rem 0.5rem',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  border: '1px solid #d1d5db',
                  borderRadius: '0.25rem',
                  cursor: 'pointer',
                  backgroundColor: filters.tag_filter_operator === 'AND' ? '#dbeafe' : '#fef3c7',
                  color: filters.tag_filter_operator === 'AND' ? '#1e40af' : '#92400e',
                }}
              >
                {filters.tag_filter_operator}
              </button>
              <span style={{ fontSize: '0.65rem', color: '#9ca3af' }}>
                {filters.tag_filter_operator === 'AND'
                  ? 'Resource must match all tags'
                  : 'Resource must match any tag'}
              </span>
            </div>
          )}
        </div>
      )}

      {/* --- Resource Types section --- */}
      <SectionHeader
        label="Resource Types"
        collapsed={typesCollapsed}
        onToggle={() => setTypesCollapsed((p) => !p)}
        badge={filters.type_filters.length}
      />
      {!typesCollapsed && (
        <div style={{ paddingLeft: '1rem' }}>
          <TypeFilterSelect
            diagramData={diagramData}
            selectedTypes={filters.type_filters}
            onTypesChange={handleTypeFiltersChange}
          />
        </div>
      )}

      {/* Empty state message (Requirement 7.5) */}
      {hasActiveFilters && filteredCount === 0 && (
        <div
          role="status"
          aria-label="No resources match filters"
          style={{
            padding: '0.75rem',
            backgroundColor: '#fef3c7',
            borderRadius: '0.375rem',
            textAlign: 'center',
            fontSize: '0.8rem',
            color: '#92400e',
            marginTop: '0.5rem',
          }}
        >
          No resources match the current filters
        </div>
      )}
    </div>
  );
}
