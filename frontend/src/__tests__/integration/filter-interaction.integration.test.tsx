import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, afterAll, afterEach, describe, it, expect, vi } from 'vitest';
import { server } from './server';
import { mockDiagramData } from './handlers';
import { DiagramPage } from '../../pages/DiagramPage';
import type { FilteredResult } from '../../types/filters';

// Mock DiagramCanvas since React Flow doesn't work well in jsdom
vi.mock('../../components/DiagramCanvas', () => ({
  DiagramCanvas: ({ data }: { data: { nodes: { id: string; name: string; resource_type: string }[] } | null }) => (
    <div data-testid="diagram-canvas">
      {data ? (
        <div data-testid="diagram-nodes">
          {data.nodes.map((node: { id: string; name: string; resource_type: string }) => (
            <div key={node.id} data-testid={`node-${node.id}`}>
              {node.name} ({node.resource_type})
            </div>
          ))}
          <span data-testid="node-count">{data.nodes.length} nodes</span>
        </div>
      ) : (
        <div data-testid="empty-state">No scan data</div>
      )}
    </div>
  ),
}));

// Mock AppLogo to avoid image fetch issues
vi.mock('../../components/AppLogo', () => ({
  AppLogo: () => <span data-testid="app-logo">Logo</span>,
}));

// Mock ExportMenu to simplify
vi.mock('../../components/ExportMenu', () => ({
  ExportMenu: () => <div data-testid="export-menu">Export</div>,
}));

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Filter interaction flow', () => {
  /**
   * Validates: Requirements 7.1, 8.1
   * Tests that tag filter AND logic and resource type filter OR logic
   * correctly filter diagram content via the API.
   */
  it('applies resource type filter and updates diagram to show only matching types', async () => {
    // Override filtered endpoint to return only ec2 nodes when type filter is applied
    const ec2FilteredResult: FilteredResult = {
      diagram: {
        nodes: [mockDiagramData.nodes[0]], // only ec2
        edges: [],
        account_id: '123456789012',
        scan_timestamp: '2024-01-15T10:30:00Z',
        total_resources: 3,
        scanned_regions: ['us-east-1'],
        failures: [],
      },
      filtered_count: 1,
      total_count: 3,
      active_filters: {
        tag_filters: [],
        type_filters: ['ec2'],
      },
    };

    server.use(
      http.get('/api/diagrams/latest/filtered', ({ request }) => {
        const url = new URL(request.url);
        const typeFilters = url.searchParams.get('type_filters');
        if (typeFilters) {
          const types = JSON.parse(typeFilters) as string[];
          const filteredNodes = mockDiagramData.nodes.filter((n) =>
            types.includes(n.resource_type)
          );
          const result: FilteredResult = {
            diagram: {
              ...mockDiagramData,
              nodes: filteredNodes,
            },
            filtered_count: filteredNodes.length,
            total_count: mockDiagramData.total_resources,
            active_filters: {
              tag_filters: [],
              type_filters: types,
            },
          };
          return HttpResponse.json(result);
        }
        return HttpResponse.json(ec2FilteredResult);
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial diagram with all 3 nodes
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Verify all resource type buttons are present (Requirement 8.1 - presents all types)
    const ec2Button = screen.getByRole('button', { name: /ec2/i, pressed: false });
    expect(ec2Button).toBeInTheDocument();

    // Click the ec2 type filter button to select it
    fireEvent.click(ec2Button);

    // Wait for filtered results - should show only 1 node
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('1 nodes');
    });

    // Verify only ec2 node is rendered
    expect(screen.getByTestId('node-ec2-1')).toBeInTheDocument();
    expect(screen.queryByTestId('node-rds-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('node-lambda-1')).not.toBeInTheDocument();
  });

  it('applies multiple resource type filters with OR logic', async () => {
    server.use(
      http.get('/api/diagrams/latest/filtered', ({ request }) => {
        const url = new URL(request.url);
        const typeFilters = url.searchParams.get('type_filters');
        if (typeFilters) {
          const types = JSON.parse(typeFilters) as string[];
          const filteredNodes = mockDiagramData.nodes.filter((n) =>
            types.includes(n.resource_type)
          );
          const result: FilteredResult = {
            diagram: {
              ...mockDiagramData,
              nodes: filteredNodes,
              edges: mockDiagramData.edges.filter(
                (e) =>
                  filteredNodes.some((n) => n.id === e.source) ||
                  filteredNodes.some((n) => n.id === e.target)
              ),
            },
            filtered_count: filteredNodes.length,
            total_count: mockDiagramData.total_resources,
            active_filters: {
              tag_filters: [],
              type_filters: types,
            },
          };
          return HttpResponse.json(result);
        }
        return HttpResponse.json({ diagram: mockDiagramData, filtered_count: 3, total_count: 3, active_filters: { tag_filters: [], type_filters: [] } });
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial render with all nodes
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Select ec2 type filter
    const ec2Button = screen.getByRole('button', { name: /ec2/i, pressed: false });
    fireEvent.click(ec2Button);

    // Wait for filter to apply (1 node: ec2)
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('1 nodes');
    });

    // Now also select lambda type filter (OR logic - should show ec2 + lambda = 2 nodes)
    const lambdaButton = screen.getByRole('button', { name: /lambda/i, pressed: false });
    fireEvent.click(lambdaButton);

    // Wait for OR filter result - ec2 + lambda = 2 nodes
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('2 nodes');
    });

    expect(screen.getByTestId('node-ec2-1')).toBeInTheDocument();
    expect(screen.getByTestId('node-lambda-1')).toBeInTheDocument();
    expect(screen.queryByTestId('node-rds-1')).not.toBeInTheDocument();
  });

  it('applies tag filters with AND logic via the tag filter input', async () => {
    const tagFilteredResult: FilteredResult = {
      diagram: {
        nodes: [mockDiagramData.nodes[0]], // only ec2 matches tag
        edges: [],
        account_id: '123456789012',
        scan_timestamp: '2024-01-15T10:30:00Z',
        total_resources: 3,
        scanned_regions: ['us-east-1'],
        failures: [],
      },
      filtered_count: 1,
      total_count: 3,
      active_filters: {
        tag_filters: [{ key: 'env', value: 'production' }],
        type_filters: [],
      },
    };

    server.use(
      http.get('/api/diagrams/latest/filtered', ({ request }) => {
        const url = new URL(request.url);
        const tagFilters = url.searchParams.get('tag_filters');
        if (tagFilters) {
          return HttpResponse.json(tagFilteredResult);
        }
        return HttpResponse.json({
          diagram: mockDiagramData,
          filtered_count: 3,
          total_count: 3,
          active_filters: { tag_filters: [], type_filters: [] },
        });
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Fill in tag filter key and value
    const keyInput = screen.getByLabelText('Tag key');
    const valueInput = screen.getByLabelText('Tag value');
    const addButton = screen.getByLabelText('Add tag filter');

    fireEvent.change(keyInput, { target: { value: 'env' } });
    fireEvent.change(valueInput, { target: { value: 'production' } });
    fireEvent.click(addButton);

    // Wait for filtered result (1 node matches the tag)
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('1 nodes');
    });

    // Verify only the matching node is visible
    expect(screen.getByTestId('node-ec2-1')).toBeInTheDocument();
    expect(screen.queryByTestId('node-rds-1')).not.toBeInTheDocument();
  });

  it('clears all filters and restores full diagram view', async () => {
    server.use(
      http.get('/api/diagrams/latest/filtered', ({ request }) => {
        const url = new URL(request.url);
        const typeFilters = url.searchParams.get('type_filters');
        if (typeFilters) {
          const types = JSON.parse(typeFilters) as string[];
          const filteredNodes = mockDiagramData.nodes.filter((n) =>
            types.includes(n.resource_type)
          );
          return HttpResponse.json({
            diagram: { ...mockDiagramData, nodes: filteredNodes },
            filtered_count: filteredNodes.length,
            total_count: mockDiagramData.total_resources,
            active_filters: { tag_filters: [], type_filters: types },
          });
        }
        return HttpResponse.json({
          diagram: mockDiagramData,
          filtered_count: 3,
          total_count: 3,
          active_filters: { tag_filters: [], type_filters: [] },
        });
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Apply a type filter
    const ec2Button = screen.getByRole('button', { name: /ec2/i, pressed: false });
    fireEvent.click(ec2Button);

    // Wait for filter to apply
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('1 nodes');
    });

    // Click "Clear All" to remove all filters
    const clearAllButton = screen.getByLabelText('Clear all filters');
    fireEvent.click(clearAllButton);

    // Wait for full diagram to be restored
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // All nodes should be visible again
    expect(screen.getByTestId('node-ec2-1')).toBeInTheDocument();
    expect(screen.getByTestId('node-rds-1')).toBeInTheDocument();
    expect(screen.getByTestId('node-lambda-1')).toBeInTheDocument();
  });

  it('displays filtered count alongside total count when filters are active', async () => {
    server.use(
      http.get('/api/diagrams/latest/filtered', () => {
        return HttpResponse.json({
          diagram: {
            ...mockDiagramData,
            nodes: [mockDiagramData.nodes[0]],
          },
          filtered_count: 1,
          total_count: 3,
          active_filters: { tag_filters: [], type_filters: ['ec2'] },
        });
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Apply a type filter
    const ec2Button = screen.getByRole('button', { name: /ec2/i, pressed: false });
    fireEvent.click(ec2Button);

    // Wait for filtered results and count display
    await waitFor(() => {
      const countDisplay = screen.getByLabelText('Filter results count');
      expect(countDisplay).toBeInTheDocument();
      expect(countDisplay).toHaveTextContent('1');
      expect(countDisplay).toHaveTextContent('3');
    });
  });
});
