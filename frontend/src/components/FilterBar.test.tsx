import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FilterBar } from './FilterBar';
import type { DiagramData } from '../types/diagram';
import type { FilterCriteria } from '../types/filters';

// Mock apiClient for TagFilterInput autocomplete
vi.mock('../api/apiClient', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue([]),
  },
}));

const mockDiagramData: DiagramData = {
  nodes: [
    { id: '1', resource_type: 'ec2', name: 'web-server', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/ec2' },
    { id: '2', resource_type: 'lambda', name: 'processor', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/lambda' },
    { id: '3', resource_type: 's3', name: 'bucket', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/s3' },
  ],
  edges: [],
  account_id: '123456789012',
  scan_timestamp: '2024-01-15T10:30:00Z',
  total_resources: 3,
  scanned_regions: ['us-east-1'],
  failures: [],
};

const emptyFilters: FilterCriteria = {
  tag_filters: [],
  type_filters: [],
};

describe('FilterBar', () => {
  const mockOnFiltersChange = vi.fn();

  beforeEach(() => {
    mockOnFiltersChange.mockClear();
  });

  describe('Rendering', () => {
    it('renders the Filters heading', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      expect(screen.getByText('Filters')).toBeInTheDocument();
    });

    it('renders TagFilterInput and TypeFilterSelect', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      expect(screen.getByLabelText('Tag key')).toBeInTheDocument();
      expect(screen.getByText('ec2')).toBeInTheDocument();
      expect(screen.getByText('lambda')).toBeInTheDocument();
      expect(screen.getByText('s3')).toBeInTheDocument();
    });
  });

  describe('Filtered count display (Requirement 7.4)', () => {
    it('shows filtered count when filters are active', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [{ key: 'Env', value: 'prod' }],
        type_filters: [],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={2}
          totalCount={3}
        />
      );
      const countDisplay = screen.getByLabelText('Filter results count');
      expect(countDisplay).toBeInTheDocument();
      expect(countDisplay.textContent).toContain('2');
      expect(countDisplay.textContent).toContain('3');
    });

    it('does not show count when no filters are active', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      expect(screen.queryByLabelText('Filter results count')).not.toBeInTheDocument();
    });

    it('shows count for type filters only', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [],
        type_filters: ['ec2'],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={1}
          totalCount={3}
        />
      );
      const countDisplay = screen.getByLabelText('Filter results count');
      expect(countDisplay.textContent).toContain('1');
      expect(countDisplay.textContent).toContain('3');
    });
  });

  describe('Empty state (Requirement 7.5)', () => {
    it('shows empty state message when filtered count is 0', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [{ key: 'Env', value: 'nonexistent' }],
        type_filters: [],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={0}
          totalCount={3}
        />
      );
      expect(
        screen.getByText('No resources match the current filters')
      ).toBeInTheDocument();
    });

    it('does not show empty state when filtered count is greater than 0', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [{ key: 'Env', value: 'prod' }],
        type_filters: [],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={2}
          totalCount={3}
        />
      );
      expect(
        screen.queryByText('No resources match the current filters')
      ).not.toBeInTheDocument();
    });

    it('does not show empty state when no filters are active', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      expect(
        screen.queryByText('No resources match the current filters')
      ).not.toBeInTheDocument();
    });
  });

  describe('Clear all filters', () => {
    it('shows Clear All button when filters are active', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [{ key: 'Env', value: 'prod' }],
        type_filters: ['ec2'],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={1}
          totalCount={3}
        />
      );
      expect(screen.getByLabelText('Clear all filters')).toBeInTheDocument();
    });

    it('clears all filters when Clear All is clicked', () => {
      const activeFilters: FilterCriteria = {
        tag_filters: [{ key: 'Env', value: 'prod' }],
        type_filters: ['ec2'],
      };
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={activeFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={1}
          totalCount={3}
        />
      );
      fireEvent.click(screen.getByLabelText('Clear all filters'));
      expect(mockOnFiltersChange).toHaveBeenCalledWith({
        tag_filters: [],
        type_filters: [],
      });
    });

    it('does not show Clear All when no filters are active', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      expect(screen.queryByLabelText('Clear all filters')).not.toBeInTheDocument();
    });
  });

  describe('Filter propagation', () => {
    it('propagates tag filter changes to parent', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      // Simulate adding a tag filter through TagFilterInput
      fireEvent.change(screen.getByLabelText('Tag key'), {
        target: { value: 'App' },
      });
      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'web' },
      });
      fireEvent.click(screen.getByLabelText('Add tag filter'));

      expect(mockOnFiltersChange).toHaveBeenCalledWith({
        tag_filters: [{ key: 'App', value: 'web' }],
        type_filters: [],
      });
    });

    it('propagates type filter changes to parent', () => {
      render(
        <FilterBar
          diagramData={mockDiagramData}
          filters={emptyFilters}
          onFiltersChange={mockOnFiltersChange}
          filteredCount={null}
          totalCount={3}
        />
      );
      fireEvent.click(screen.getByText('ec2'));

      expect(mockOnFiltersChange).toHaveBeenCalledWith({
        tag_filters: [],
        type_filters: ['ec2'],
      });
    });
  });
});
