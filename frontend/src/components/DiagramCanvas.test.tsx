import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DiagramCanvas } from './DiagramCanvas';
import type { DiagramData } from '../types/diagram';

// Mock @xyflow/react since it requires browser-specific APIs
vi.mock('@xyflow/react', () => {
  const ReactFlow = ({ children, minZoom, maxZoom, fitView }: {
    children?: React.ReactNode;
    minZoom?: number;
    maxZoom?: number;
    fitView?: boolean;
    [key: string]: unknown;
  }) => (
    <div
      data-testid="react-flow"
      data-min-zoom={minZoom}
      data-max-zoom={maxZoom}
      data-fit-view={fitView}
    >
      {children}
    </div>
  );

  const Background = () => <div data-testid="react-flow-background" />;
  const Controls = () => <div data-testid="react-flow-controls" />;

  return {
    ReactFlow,
    Background,
    Controls,
    useNodesState: (initialNodes: unknown[]) => [initialNodes, vi.fn(), vi.fn()],
    useEdgesState: (initialEdges: unknown[]) => [initialEdges, vi.fn(), vi.fn()],
  };
});

const mockDiagramData: DiagramData = {
  nodes: [
    {
      id: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123',
      resource_type: 'ec2',
      name: 'web-server-01',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/images/icons/ec2',
    },
    {
      id: 'arn:aws:ec2:us-east-1:123456789012:security-group/sg-xyz789',
      resource_type: 'security_group',
      name: 'web-sg',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/images/icons/security_group',
    },
  ],
  edges: [
    {
      id: 'edge-1',
      source: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123',
      target: 'arn:aws:ec2:us-east-1:123456789012:security-group/sg-xyz789',
      category: 'network',
      derived_from: 'SecurityGroups',
      label: null,
    },
  ],
  account_id: '123456789012',
  scan_timestamp: '2024-01-15T10:30:00Z',
  total_resources: 2,
  scanned_regions: ['us-east-1'],
  failures: [],
};

describe('DiagramCanvas', () => {
  describe('Empty state (Requirement 5.7)', () => {
    it('renders EmptyState when data is null', () => {
      render(<DiagramCanvas data={null} />);
      expect(screen.getByRole('status')).toBeInTheDocument();
      expect(screen.getByText('No Infrastructure Diagram Available')).toBeInTheDocument();
    });

    it('renders EmptyState when data has no nodes', () => {
      const emptyData: DiagramData = {
        ...mockDiagramData,
        nodes: [],
        edges: [],
      };
      render(<DiagramCanvas data={emptyData} />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows call-to-action to configure credentials', () => {
      render(<DiagramCanvas data={null} />);
      const link = screen.getByText('Configure Credentials & Scan');
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/settings');
    });
  });

  describe('Diagram rendering with data', () => {
    it('renders ReactFlow component when valid data is provided', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      expect(screen.getByTestId('react-flow')).toBeInTheDocument();
    });

    it('configures minZoom to 0.25 (Requirement 5.5)', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-min-zoom', '0.25');
    });

    it('configures maxZoom to 4.0 (Requirement 5.5)', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-max-zoom', '4');
    });

    it('enables fitView for initial load (Requirement 5.5)', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-fit-view', 'true');
    });

    it('renders Background and Controls components', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      expect(screen.getByTestId('react-flow-background')).toBeInTheDocument();
      expect(screen.getByTestId('react-flow-controls')).toBeInTheDocument();
    });
  });
});

describe('EmptyState', () => {
  it('has an accessible role of status', () => {
    render(<DiagramCanvas data={null} />);
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      'No scan data available'
    );
  });
});
