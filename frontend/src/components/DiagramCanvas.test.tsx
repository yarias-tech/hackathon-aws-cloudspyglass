import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DiagramCanvas, rerouteEdgesForCollapsedContainers } from './DiagramCanvas';
import type { DiagramData } from '../types/diagram';
import type { Edge } from '@xyflow/react';
import type { ContainerMetadata } from '../types/hierarchy';

// Track callbacks registered with ReactFlow for testing interactive behaviors
let capturedOnNodeMouseEnter: ((...args: unknown[]) => void) | undefined;
let capturedOnNodeMouseLeave: ((...args: unknown[]) => void) | undefined;
let capturedOnNodeClick: ((...args: unknown[]) => void) | undefined;

const mockSetEdges = vi.fn();
const mockFitView = vi.fn();

// Mock @xyflow/react since it requires browser-specific APIs
vi.mock('@xyflow/react', () => {
  const ReactFlow = ({ children, minZoom, maxZoom, fitView, onNodeMouseEnter, onNodeMouseLeave, onNodeClick }: {
    children?: React.ReactNode;
    minZoom?: number;
    maxZoom?: number;
    fitView?: boolean;
    onNodeMouseEnter?: (...args: unknown[]) => void;
    onNodeMouseLeave?: (...args: unknown[]) => void;
    onNodeClick?: (...args: unknown[]) => void;
    [key: string]: unknown;
  }) => {
    capturedOnNodeMouseEnter = onNodeMouseEnter;
    capturedOnNodeMouseLeave = onNodeMouseLeave;
    capturedOnNodeClick = onNodeClick;
    return (
      <div
        data-testid="react-flow"
        data-min-zoom={minZoom}
        data-max-zoom={maxZoom}
        data-fit-view={fitView}
      >
        {children}
      </div>
    );
  };

  const Background = () => <div data-testid="react-flow-background" />;
  const Controls = () => <div data-testid="react-flow-controls" />;
  const ReactFlowProvider = ({ children }: { children: React.ReactNode }) => <>{children}</>;

  return {
    ReactFlow,
    ReactFlowProvider,
    Background,
    Controls,
    useReactFlow: () => ({ fitView: mockFitView }),
    useNodesState: (initialNodes: unknown[]) => [initialNodes, vi.fn(), vi.fn()],
    useEdgesState: (initialEdges: unknown[]) => [initialEdges, mockSetEdges, vi.fn()],
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
  hierarchy: null,
};

describe('DiagramCanvas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnNodeMouseEnter = undefined;
    capturedOnNodeMouseLeave = undefined;
    capturedOnNodeClick = undefined;
  });

  describe('Empty state', () => {
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

    it('shows filter empty state when isFiltered is true', () => {
      render(<DiagramCanvas data={{ ...mockDiagramData, nodes: [], edges: [] }} isFiltered={true} />);
      expect(screen.getByText('No Resources Match Current Filters')).toBeInTheDocument();
    });
  });

  describe('Zoom configuration (Requirement 8.1)', () => {
    it('configures minZoom to 0.1', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-min-zoom', '0.1');
    });

    it('configures maxZoom to 5.0', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-max-zoom', '5');
    });
  });

  describe('Fit view on initial load (Requirement 8.2)', () => {
    it('enables fitView for initial load', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const reactFlow = screen.getByTestId('react-flow');
      expect(reactFlow).toHaveAttribute('data-fit-view', 'true');
    });
  });

  describe('Fit view button (Requirement 8.8)', () => {
    it('renders a dedicated fit view button', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const button = screen.getByTestId('fit-view-button');
      expect(button).toBeInTheDocument();
      expect(button).toHaveAttribute('aria-label', 'Fit view');
    });

    it('calls fitView when clicked', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      const button = screen.getByTestId('fit-view-button');
      fireEvent.click(button);
      expect(mockFitView).toHaveBeenCalledWith({ padding: 0.2 });
    });
  });

  describe('Node click emits selection event (Requirement 8.5)', () => {
    it('calls onNodeClick with node ID when a node is clicked', () => {
      const handleClick = vi.fn();
      render(<DiagramCanvas data={mockDiagramData} onNodeClick={handleClick} />);

      // Simulate React Flow calling onNodeClick
      expect(capturedOnNodeClick).toBeDefined();
      capturedOnNodeClick!({}, { id: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123', type: 'resource' });
      expect(handleClick).toHaveBeenCalledWith('arn:aws:ec2:us-east-1:123456789012:instance/i-abc123');
    });
  });

  describe('Hover highlight/dim (Requirements 8.6, 8.7)', () => {
    it('registers onNodeMouseEnter and onNodeMouseLeave handlers', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      expect(capturedOnNodeMouseEnter).toBeDefined();
      expect(capturedOnNodeMouseLeave).toBeDefined();
    });

    it('calls setEdges with highlight logic on resource node hover', () => {
      render(<DiagramCanvas data={mockDiagramData} />);

      // Simulate hovering over a resource node
      capturedOnNodeMouseEnter!(
        {},
        { id: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123', type: 'resource' }
      );

      // setEdges should be called with an updater function
      expect(mockSetEdges).toHaveBeenCalled();
    });

    it('does not apply highlight behavior for non-resource nodes', () => {
      render(<DiagramCanvas data={mockDiagramData} />);

      // Clear any calls from initial render/effect
      mockSetEdges.mockClear();

      // Simulate hovering over a container node
      capturedOnNodeMouseEnter!(
        {},
        { id: 'container-1', type: 'container' }
      );

      // setEdges should NOT be called for container nodes
      expect(mockSetEdges).not.toHaveBeenCalled();
    });

    it('restores edges on mouse leave from resource node', () => {
      render(<DiagramCanvas data={mockDiagramData} />);

      capturedOnNodeMouseLeave!(
        {},
        { id: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123', type: 'resource' }
      );

      expect(mockSetEdges).toHaveBeenCalled();
    });
  });

  describe('Diagram rendering with data', () => {
    it('renders ReactFlow component when valid data is provided', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      expect(screen.getByTestId('react-flow')).toBeInTheDocument();
    });

    it('renders Background and Controls components', () => {
      render(<DiagramCanvas data={mockDiagramData} />);
      expect(screen.getByTestId('react-flow-background')).toBeInTheDocument();
      expect(screen.getByTestId('react-flow-controls')).toBeInTheDocument();
    });
  });
});

describe('rerouteEdgesForCollapsedContainers (Requirement 8.9)', () => {
  const makeContainerMap = (): Map<string, ContainerMetadata> => {
    const map = new Map<string, ContainerMetadata>();
    map.set('vpc-1', {
      id: 'vpc-1',
      name: 'VPC',
      type: 'vpc',
      parent_id: 'region-1',
      subnet_type: null,
      icon_key: 'vpc',
      resources: ['res-a', 'res-b'],
      children: ['subnet-1'],
    });
    map.set('subnet-1', {
      id: 'subnet-1',
      name: 'Subnet',
      type: 'subnet',
      parent_id: 'vpc-1',
      subnet_type: 'private',
      icon_key: 'subnet',
      resources: ['res-c'],
      children: [],
    });
    return map;
  };

  it('returns edges unchanged when no containers are collapsed', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'res-a', target: 'res-c', type: 'relationship', data: { category: 'network' } },
    ];
    const result = rerouteEdgesForCollapsedContainers(edges, new Set(), makeContainerMap());
    expect(result).toEqual(edges);
  });

  it('reroutes edge to collapsed container when target is a descendant', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'external-node', target: 'res-c', type: 'relationship', data: { category: 'network' } },
    ];
    const collapsed = new Set(['vpc-1']);
    const result = rerouteEdgesForCollapsedContainers(edges, collapsed, makeContainerMap());

    expect(result).toHaveLength(1);
    expect(result[0].target).toBe('vpc-1');
    expect(result[0].source).toBe('external-node');
  });

  it('reroutes edge to collapsed container when source is a descendant', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'res-a', target: 'external-node', type: 'relationship', data: { category: 'network' } },
    ];
    const collapsed = new Set(['vpc-1']);
    const result = rerouteEdgesForCollapsedContainers(edges, collapsed, makeContainerMap());

    expect(result).toHaveLength(1);
    expect(result[0].source).toBe('vpc-1');
    expect(result[0].target).toBe('external-node');
  });

  it('removes self-referencing edges when both endpoints are in the same collapsed container', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'res-a', target: 'res-b', type: 'relationship', data: { category: 'network' } },
    ];
    const collapsed = new Set(['vpc-1']);
    const result = rerouteEdgesForCollapsedContainers(edges, collapsed, makeContainerMap());

    // Both res-a and res-b are in vpc-1, so after rerouting source=vpc-1, target=vpc-1 → removed
    expect(result).toHaveLength(0);
  });

  it('deduplicates rerouted edges pointing to the same container', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'res-a', target: 'external-node', type: 'relationship', data: { category: 'network' } },
      { id: 'e2', source: 'res-b', target: 'external-node', type: 'relationship', data: { category: 'network' } },
    ];
    const collapsed = new Set(['vpc-1']);
    const result = rerouteEdgesForCollapsedContainers(edges, collapsed, makeContainerMap());

    // Both reroute to vpc-1 → external-node with same category, should deduplicate
    expect(result).toHaveLength(1);
    expect(result[0].source).toBe('vpc-1');
    expect(result[0].target).toBe('external-node');
  });

  it('handles nested collapse: resources in child containers are rerouted to parent', () => {
    const edges: Edge[] = [
      { id: 'e1', source: 'res-c', target: 'external-node', type: 'relationship', data: { category: 'data' } },
    ];
    // Collapse vpc-1, which contains subnet-1 which contains res-c
    const collapsed = new Set(['vpc-1']);
    const result = rerouteEdgesForCollapsedContainers(edges, collapsed, makeContainerMap());

    expect(result).toHaveLength(1);
    expect(result[0].source).toBe('vpc-1');
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
