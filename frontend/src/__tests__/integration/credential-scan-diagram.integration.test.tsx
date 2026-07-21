import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, afterAll, afterEach, describe, it, expect, vi } from 'vitest';
import { server } from './server';
import { mockConnectedStatus, mockDiagramData } from './handlers';
import { SettingsPage } from '../../pages/SettingsPage';
import { DiagramPage } from '../../pages/DiagramPage';

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

describe('Credential submission → Scan → Diagram rendering flow', () => {
  /**
   * Validates: Requirements 5.1
   * Tests that diagram renders resources as nodes with name, type, and icon
   * after a successful credential submission and scan.
   */
  it('renders diagram with resource nodes after successful credential submission', async () => {
    // First, render SettingsPage and submit credentials
    const { unmount } = render(
      <MemoryRouter initialEntries={['/settings']}>
        <SettingsPage />
      </MemoryRouter>
    );

    // Wait for initial status to load
    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Disconnected');
    });

    // Fill in credential form
    const accessKeyInput = screen.getByTestId('access-key-input');
    const secretKeyInput = screen.getByTestId('secret-key-input');

    fireEvent.change(accessKeyInput, { target: { value: 'AKIAIOSFODNN7EXAMPLE' } });
    fireEvent.change(secretKeyInput, { target: { value: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' } });

    // Submit credentials
    const submitButton = screen.getByTestId('submit-credentials-button');
    fireEvent.click(submitButton);

    // Wait for credentials to be validated and status to update
    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Connected');
    });

    // Verify account ID is displayed
    expect(screen.getByTestId('account-id')).toHaveTextContent('123456789012');

    unmount();

    // Now render DiagramPage — it should load diagram data
    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for diagram to render with nodes
    await waitFor(() => {
      expect(screen.getByTestId('diagram-canvas')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Verify individual resource nodes display name and type (Requirement 5.1)
    expect(screen.getByTestId('node-ec2-1')).toHaveTextContent('web-server-1 (ec2)');
    expect(screen.getByTestId('node-rds-1')).toHaveTextContent('main-database (rds)');
    expect(screen.getByTestId('node-lambda-1')).toHaveTextContent('api-handler (lambda)');
  });

  it('triggers a scan and updates the diagram with new data', async () => {
    // Override scan endpoint to return new data after scan
    const updatedDiagramData = {
      ...mockDiagramData,
      nodes: [
        ...mockDiagramData.nodes,
        {
          id: 's3-1',
          resource_type: 's3',
          name: 'data-bucket',
          region: 'us-east-1',
          is_external: false,
          is_unresolved: false,
          icon_url: '/api/images/icons/s3',
        },
      ],
      total_resources: 4,
    };

    let scanTriggered = false;

    server.use(
      http.post('/api/scan', () => {
        scanTriggered = true;
        return HttpResponse.json({ status: 'completed' });
      }),
      http.get('/api/diagrams/latest', () => {
        // After scan, return updated data
        if (scanTriggered) {
          return HttpResponse.json(updatedDiagramData);
        }
        return HttpResponse.json(mockDiagramData);
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial diagram load
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Click the manual refresh/scan button
    const scanButton = screen.getByTestId('manual-refresh-button');
    fireEvent.click(scanButton);

    // Wait for diagram to update with new data (4 nodes)
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('4 nodes');
    });

    // Verify the new resource appears
    expect(screen.getByTestId('node-s3-1')).toHaveTextContent('data-bucket (s3)');
  });

  it('displays credential status as Connected with account details after submission', async () => {
    server.use(
      http.post('/api/credentials', () => {
        return HttpResponse.json(mockConnectedStatus);
      })
    );

    render(
      <MemoryRouter initialEntries={['/settings']}>
        <SettingsPage />
      </MemoryRouter>
    );

    // Wait for initial disconnected status
    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Disconnected');
    });

    // Fill and submit credentials
    fireEvent.change(screen.getByTestId('access-key-input'), {
      target: { value: 'AKIAIOSFODNN7EXAMPLE' },
    });
    fireEvent.change(screen.getByTestId('secret-key-input'), {
      target: { value: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' },
    });
    fireEvent.click(screen.getByTestId('submit-credentials-button'));

    // Verify connection result
    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Connected');
    });
    expect(screen.getByTestId('account-id')).toHaveTextContent('123456789012');
    expect(screen.getByTestId('credential-source')).toHaveTextContent('UI-provided');
  });

  it('handles scan failure gracefully and retains current diagram', async () => {
    server.use(
      http.post('/api/scan', () => {
        return HttpResponse.json(
          {
            error_code: 'SCAN_FAILED',
            message: 'AWS credentials expired',
            details: null,
            timestamp: '2024-01-15T10:30:00Z',
            recoverable: true,
          },
          { status: 500 }
        );
      })
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <DiagramPage />
      </MemoryRouter>
    );

    // Wait for initial diagram load
    await waitFor(() => {
      expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
    });

    // Trigger scan that will fail
    const scanButton = screen.getByTestId('manual-refresh-button');
    fireEvent.click(scanButton);

    // Diagram data should still be present (not cleared on failure)
    await waitFor(() => {
      expect(screen.getByTestId('scan-error-banner')).toBeInTheDocument();
    });

    // Verify diagram nodes are still rendered
    expect(screen.getByTestId('node-count')).toHaveTextContent('3 nodes');
  });
});
