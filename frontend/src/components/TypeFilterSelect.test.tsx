import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TypeFilterSelect } from './TypeFilterSelect';
import type { DiagramData } from '../types/diagram';

const mockDiagramData: DiagramData = {
  nodes: [
    { id: '1', resource_type: 'ec2', name: 'web-server', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/ec2' },
    { id: '2', resource_type: 'lambda', name: 'processor', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/lambda' },
    { id: '3', resource_type: 'ec2', name: 'api-server', region: 'us-west-2', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/ec2' },
    { id: '4', resource_type: 's3', name: 'data-bucket', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/s3' },
    { id: '5', resource_type: 'rds', name: 'database', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/rds' },
  ],
  edges: [],
  account_id: '123456789012',
  scan_timestamp: '2024-01-15T10:30:00Z',
  total_resources: 5,
  scanned_regions: ['us-east-1', 'us-west-2'],
  failures: [],
};

describe('TypeFilterSelect', () => {
  const mockOnTypesChange = vi.fn();

  beforeEach(() => {
    mockOnTypesChange.mockClear();
  });

  describe('Rendering (Requirement 8.1)', () => {
    it('extracts and displays distinct resource types from diagram data', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={[]}
          onTypesChange={mockOnTypesChange}
        />
      );
      expect(screen.getByText('ec2')).toBeInTheDocument();
      expect(screen.getByText('lambda')).toBeInTheDocument();
      expect(screen.getByText('s3')).toBeInTheDocument();
      expect(screen.getByText('rds')).toBeInTheDocument();
    });

    it('sorts resource types alphabetically', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={[]}
          onTypesChange={mockOnTypesChange}
        />
      );
      const buttons = screen.getAllByRole('button', { pressed: false });
      // Filter out "All" and "None" buttons
      const typeButtons = buttons.filter(
        (btn) => btn.getAttribute('aria-pressed') !== null
      );
      const texts = typeButtons.map((btn) => btn.textContent);
      expect(texts).toEqual(['ec2', 'lambda', 'rds', 's3']);
    });

    it('renders nothing when diagram data is null', () => {
      const { container } = render(
        <TypeFilterSelect
          diagramData={null}
          selectedTypes={[]}
          onTypesChange={mockOnTypesChange}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders nothing when diagram has no nodes', () => {
      const emptyData: DiagramData = {
        ...mockDiagramData,
        nodes: [],
      };
      const { container } = render(
        <TypeFilterSelect
          diagramData={emptyData}
          selectedTypes={[]}
          onTypesChange={mockOnTypesChange}
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('shows selection count when types are selected', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={['ec2', 'lambda']}
          onTypesChange={mockOnTypesChange}
        />
      );
      expect(screen.getByText('(2/4)')).toBeInTheDocument();
    });
  });

  describe('Selection interactions', () => {
    it('adds type to selection when clicked', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={[]}
          onTypesChange={mockOnTypesChange}
        />
      );
      fireEvent.click(screen.getByText('ec2'));
      expect(mockOnTypesChange).toHaveBeenCalledWith(['ec2']);
    });

    it('removes type from selection when already selected', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={['ec2', 'lambda']}
          onTypesChange={mockOnTypesChange}
        />
      );
      fireEvent.click(screen.getByText('ec2'));
      expect(mockOnTypesChange).toHaveBeenCalledWith(['lambda']);
    });

    it('selects all types when All button is clicked', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={['ec2']}
          onTypesChange={mockOnTypesChange}
        />
      );
      fireEvent.click(screen.getByLabelText('Select all resource types'));
      expect(mockOnTypesChange).toHaveBeenCalledWith(['ec2', 'lambda', 'rds', 's3']);
    });

    it('clears all selections when None button is clicked', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={['ec2', 'lambda']}
          onTypesChange={mockOnTypesChange}
        />
      );
      fireEvent.click(screen.getByLabelText('Clear all resource type filters'));
      expect(mockOnTypesChange).toHaveBeenCalledWith([]);
    });

    it('marks selected buttons with aria-pressed=true', () => {
      render(
        <TypeFilterSelect
          diagramData={mockDiagramData}
          selectedTypes={['ec2']}
          onTypesChange={mockOnTypesChange}
        />
      );
      const ec2Button = screen.getByText('ec2');
      expect(ec2Button).toHaveAttribute('aria-pressed', 'true');

      const lambdaButton = screen.getByText('lambda');
      expect(lambdaButton).toHaveAttribute('aria-pressed', 'false');
    });
  });
});
