import { useCallback } from 'react';
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

/**
 * FilterBar orchestrates tag and resource-type filter controls.
 *
 * - Combines TagFilterInput and TypeFilterSelect components
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
        padding: '0.75rem',
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#fafafa',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
      }}
    >
      {/* Filter status bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#111827' }}>
          Filters
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Filtered count display (Requirement 7.4) */}
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

      {/* Tag filters */}
      <TagFilterInput
        filters={filters.tag_filters}
        onFiltersChange={handleTagFiltersChange}
      />

      {/* Tag filter operator toggle — only show when multiple tag filters exist */}
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

      {/* Type filters */}
      <TypeFilterSelect
        diagramData={diagramData}
        selectedTypes={filters.type_filters}
        onTypesChange={handleTypeFiltersChange}
      />

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
          }}
        >
          No resources match the current filters
        </div>
      )}
    </div>
  );
}
