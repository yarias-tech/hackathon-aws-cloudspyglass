import { useState, useEffect, useCallback } from 'react';
import { DiagramCanvas } from '../components/DiagramCanvas';
import { FilterBar } from '../components/FilterBar';
import { DetailPanel } from '../components/DetailPanel';
import { apiClient, ApiError } from '../api/apiClient';
import type { DiagramData } from '../types/diagram';
import type { FilterCriteria, FilteredResult } from '../types/filters';
import type { Resource } from '../types/resources';
import type { ErrorResponse } from '../types/errors';

/**
 * Placeholder ScanControls component.
 * Will be properly implemented in task 16.1.
 */
function ScanControls() {
  return (
    <button
      type="button"
      style={{
        padding: '0.5rem 1rem',
        backgroundColor: '#2563eb',
        color: '#fff',
        border: 'none',
        borderRadius: '0.375rem',
        cursor: 'pointer',
        fontSize: '0.8rem',
        fontWeight: 500,
      }}
      aria-label="Scan controls"
    >
      Scan
    </button>
  );
}

/**
 * Placeholder ExportMenu component.
 * Will be properly implemented in task 17.1.
 */
function ExportMenu() {
  return (
    <button
      type="button"
      style={{
        padding: '0.5rem 1rem',
        backgroundColor: '#6b7280',
        color: '#fff',
        border: 'none',
        borderRadius: '0.375rem',
        cursor: 'pointer',
        fontSize: '0.8rem',
        fontWeight: 500,
      }}
      aria-label="Export menu"
    >
      Export
    </button>
  );
}

/** Determine whether filter criteria has any active filters */
function hasActiveFilters(filters: FilterCriteria): boolean {
  return filters.tag_filters.length > 0 || filters.type_filters.length > 0;
}

/** Build query string from FilterCriteria for the filtered API endpoint */
function buildFilterParams(filters: FilterCriteria): string {
  const params = new URLSearchParams();
  if (filters.tag_filters.length > 0) {
    params.set('tag_filters', JSON.stringify(filters.tag_filters));
  }
  if (filters.type_filters.length > 0) {
    params.set('type_filters', JSON.stringify(filters.type_filters));
  }
  return params.toString();
}

/**
 * DiagramPage is the main route (/) for CloudSpyglass.
 *
 * Integrates:
 * - DiagramCanvas for rendering the infrastructure diagram
 * - FilterBar for tag and resource-type filtering
 * - ScanControls (placeholder) for triggering scans
 * - ExportMenu (placeholder) for exporting diagrams
 * - DetailPanel for showing resource metadata on node click
 *
 * Requirements: 5.1, 7.1, 8.1
 */
export function DiagramPage() {
  // Diagram data state
  const [diagramData, setDiagramData] = useState<DiagramData | null>(null);
  const [filteredData, setFilteredData] = useState<DiagramData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [filters, setFilters] = useState<FilterCriteria>({
    tag_filters: [],
    type_filters: [],
  });
  const [filteredCount, setFilteredCount] = useState<number | null>(null);

  // Detail panel state
  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<ErrorResponse | null>(null);

  // Fetch initial diagram data on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchDiagram() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.get<DiagramData>('/diagrams/latest');
        if (!cancelled) {
          setDiagramData(data);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError('Failed to load diagram data');
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchDiagram();
    return () => { cancelled = true; };
  }, []);

  // Fetch filtered data when filters change
  useEffect(() => {
    if (!hasActiveFilters(filters)) {
      setFilteredData(null);
      setFilteredCount(null);
      return;
    }

    let cancelled = false;

    async function fetchFiltered() {
      try {
        const queryString = buildFilterParams(filters);
        const result = await apiClient.get<FilteredResult>(
          `/diagrams/latest/filtered?${queryString}`
        );
        if (!cancelled) {
          setFilteredData(result.diagram);
          setFilteredCount(result.filtered_count);
        }
      } catch (err) {
        if (!cancelled) {
          // On filter fetch error, keep showing unfiltered data
          setFilteredData(null);
          setFilteredCount(null);
        }
      }
    }

    fetchFiltered();
    return () => { cancelled = true; };
  }, [filters]);

  // Handle filter changes
  const handleFiltersChange = useCallback((newFilters: FilterCriteria) => {
    setFilters(newFilters);
  }, []);

  // Handle node click to show detail panel.
  // Exposed via window for DiagramCanvas onNodeClick integration (React Flow node click).
  const handleNodeClick = useCallback(async (resourceId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    setSelectedResource(null);

    try {
      const resource = await apiClient.get<Resource>(`/resources/${resourceId}`);
      setSelectedResource(resource);
    } catch (err) {
      if (err instanceof ApiError) {
        setDetailError(err.errorResponse);
      } else {
        setDetailError({
          error_code: 'UNKNOWN_ERROR',
          message: 'Failed to load resource details',
          details: null,
          timestamp: new Date().toISOString(),
          recoverable: true,
        });
      }
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // Store handleNodeClick on the window object for React Flow node click event integration.
  // This will be wired directly when DiagramCanvas adds onNodeClick prop support.
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__cloudspyglass_onNodeClick = handleNodeClick;
    return () => {
      delete (window as unknown as Record<string, unknown>).__cloudspyglass_onNodeClick;
    };
  }, [handleNodeClick]);

  // Handle detail panel close
  const handleDetailClose = useCallback(() => {
    setSelectedResource(null);
    setDetailError(null);
  }, []);

  // Determine which data to pass to the canvas
  const displayData = hasActiveFilters(filters) ? filteredData : diagramData;
  const totalCount = diagramData?.total_resources ?? 0;

  // Loading state
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          flexDirection: 'column',
          gap: '1rem',
        }}
        aria-label="Loading diagram"
      >
        <div
          style={{
            width: '2rem',
            height: '2rem',
            border: '3px solid #e5e7eb',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
        />
        <span style={{ color: '#6b7280', fontSize: '0.9rem' }}>
          Loading infrastructure diagram…
        </span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          flexDirection: 'column',
          gap: '1rem',
        }}
        role="alert"
      >
        <span style={{ color: '#dc2626', fontSize: '1rem', fontWeight: 500 }}>
          {error}
        </span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '0.375rem',
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          padding: '0.5rem 1rem',
          borderBottom: '1px solid #e5e7eb',
          backgroundColor: '#fff',
          gap: '0.5rem',
        }}
      >
        <ScanControls />
        <ExportMenu />
      </div>

      {/* Filter bar */}
      <FilterBar
        diagramData={diagramData}
        filters={filters}
        onFiltersChange={handleFiltersChange}
        filteredCount={filteredCount}
        totalCount={totalCount}
      />

      {/* Main content area */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <DiagramCanvas data={displayData} />

        {/* Detail panel overlay */}
        <DetailPanel
          resource={selectedResource}
          loading={detailLoading}
          error={detailError}
          onClose={handleDetailClose}
        />
      </div>
    </div>
  );
}
