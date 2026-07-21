import { useMemo, useCallback } from 'react';
import type { DiagramData } from '../types/diagram';

interface TypeFilterSelectProps {
  /** Current diagram data to extract available resource types */
  diagramData: DiagramData | null;
  /** Currently selected resource types */
  selectedTypes: string[];
  /** Callback when selection changes */
  onTypesChange: (types: string[]) => void;
}

/**
 * TypeFilterSelect presents all resource types found in scan data as selectable options.
 *
 * - Extracts distinct resource_type values from DiagramData nodes (Requirement 8.1)
 * - Applies OR logic across selected types
 * - Provides select-all and clear-all controls
 */
export function TypeFilterSelect({
  diagramData,
  selectedTypes,
  onTypesChange,
}: TypeFilterSelectProps) {
  // Extract distinct resource types from diagram nodes
  const availableTypes = useMemo(() => {
    if (!diagramData || !diagramData.nodes.length) return [];
    const typeSet = new Set(diagramData.nodes.map((node) => node.resource_type));
    return Array.from(typeSet).sort();
  }, [diagramData]);

  const handleToggleType = useCallback(
    (type: string) => {
      if (selectedTypes.includes(type)) {
        onTypesChange(selectedTypes.filter((t) => t !== type));
      } else {
        onTypesChange([...selectedTypes, type]);
      }
    },
    [selectedTypes, onTypesChange]
  );

  const handleSelectAll = useCallback(() => {
    onTypesChange([...availableTypes]);
  }, [availableTypes, onTypesChange]);

  const handleClearAll = useCallback(() => {
    onTypesChange([]);
  }, [onTypesChange]);

  if (availableTypes.length === 0) {
    return null;
  }

  return (
    <div className="type-filter-select">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151' }}>
          Resource Types
          {selectedTypes.length > 0 && (
            <span style={{ color: '#6b7280', fontWeight: 400 }}> ({selectedTypes.length}/{availableTypes.length})</span>
          )}
        </span>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={handleSelectAll}
            disabled={selectedTypes.length === availableTypes.length}
            aria-label="Select all resource types"
            style={{
              background: 'none',
              border: 'none',
              cursor: selectedTypes.length === availableTypes.length ? 'default' : 'pointer',
              fontSize: '0.625rem',
              color: selectedTypes.length === availableTypes.length ? '#9ca3af' : '#2563eb',
              padding: 0,
            }}
          >
            All
          </button>
          <button
            onClick={handleClearAll}
            disabled={selectedTypes.length === 0}
            aria-label="Clear all resource type filters"
            style={{
              background: 'none',
              border: 'none',
              cursor: selectedTypes.length === 0 ? 'default' : 'pointer',
              fontSize: '0.625rem',
              color: selectedTypes.length === 0 ? '#9ca3af' : '#2563eb',
              padding: 0,
            }}
          >
            None
          </button>
        </div>
      </div>

      <div
        role="group"
        aria-label="Resource type filters"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.25rem',
        }}
      >
        {availableTypes.map((type) => {
          const isSelected = selectedTypes.includes(type);
          return (
            <button
              key={type}
              onClick={() => handleToggleType(type)}
              aria-pressed={isSelected}
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.7rem',
                borderRadius: '0.25rem',
                border: `1px solid ${isSelected ? '#2563eb' : '#d1d5db'}`,
                backgroundColor: isSelected ? '#eff6ff' : '#ffffff',
                color: isSelected ? '#1d4ed8' : '#374151',
                cursor: 'pointer',
                fontWeight: isSelected ? 500 : 400,
                transition: 'all 0.15s',
              }}
            >
              {type}
            </button>
          );
        })}
      </div>
    </div>
  );
}
