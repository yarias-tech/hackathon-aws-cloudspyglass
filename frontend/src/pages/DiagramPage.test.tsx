import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DiagramPage } from './DiagramPage';
import type { DiagramData } from '../types/diagram';

// Mock the apiClient module
vi.mock('../api/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    statusCode: number;
    errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean };
    constructor(statusCode: number, errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean }) {
      super(errorResponse.message);
      this.statusCode = statusCode;
      this.errorResponse = errorResponse;
    }
  },
}));

// Mock DiagramCanvas to avoid React Flow complexity in tests
vi.mock('../components/DiagramCanvas', () => ({
  DiagramCanvas: ({ data }: { data: DiagramData | null }) => (
    <div data-testid="diagram-canvas">{data ? `${data.nodes.length} nodes` : 'no data'}</div>
  ),
}));

// Mock FilterBar
vi.mock('../components/FilterBar', () => ({
  FilterBar: () => <div data-testid="filter-bar">FilterBar</div>,
}));

// Mock DetailPanel
vi.mock('../components/DetailPanel', () => ({
  DetailPanel: () => <div data-testid="detail-panel">DetailPanel</div>,
}));

const { apiClient } = await import('../api/apiClient');

const mockDiagramData: DiagramData = {
  nodes: [
    {
      id: 'node-1',
      resource_type: 'ec2',
      name: 'my-instance',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/icons/ec2',
    },
  ],
  edges: [],
  account_id: '123456789012',
  scan_timestamp: '2024-01-01T00:00:00Z',
  total_resources: 1,
  scanned_regions: ['us-east-1'],
  failures: [],
};

function renderDiagramPage() {
  return render(
    <BrowserRouter>
      <DiagramPage />
    </BrowserRouter>
  );
}

describe('DiagramPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    renderDiagramPage();
    expect(screen.getByLabelText('Loading diagram')).toBeInTheDocument();
  });

  it('renders diagram data after successful fetch', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockDiagramData);
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByTestId('diagram-canvas')).toHaveTextContent('1 nodes');
    });
  });

  it('shows error state when fetch fails', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Network error'));
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Failed to load diagram data')).toBeInTheDocument();
    });
  });

  it('renders header with ScanControls and ExportMenu placeholders', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockDiagramData);
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByText('CloudSpyglass')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Scan controls')).toBeInTheDocument();
    expect(screen.getByLabelText('Export menu')).toBeInTheDocument();
  });

  it('renders FilterBar component', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockDiagramData);
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByTestId('filter-bar')).toBeInTheDocument();
    });
  });

  it('renders DetailPanel component', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockDiagramData);
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByTestId('detail-panel')).toBeInTheDocument();
    });
  });

  it('shows retry button on error', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('fail'));
    renderDiagramPage();

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });
  });
});
