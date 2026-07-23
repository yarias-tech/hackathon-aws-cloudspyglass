import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ScanControls } from './ScanControls';
import type { DiagramData } from '../types/diagram';

// Mock the apiClient module
vi.mock('../api/apiClient', () => {
  const ApiError = class extends Error {
    statusCode: number;
    errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean };
    constructor(statusCode: number, errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean }) {
      super(errorResponse.message);
      this.name = 'ApiError';
      this.statusCode = statusCode;
      this.errorResponse = errorResponse;
    }
    get recoverable() { return this.errorResponse.recoverable; }
    get errorCode() { return this.errorResponse.error_code; }
  };

  return {
    ApiError,
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
  };
});

import { apiClient, ApiError } from '../api/apiClient';

const mockDiagramData: DiagramData = {
  nodes: [{ id: 'node-1', resource_type: 'ec2', name: 'test-instance', region: 'us-east-1', is_external: false, is_unresolved: false, icon_url: '/api/images/icons/ec2' }],
  edges: [],
  account_id: '123456789012',
  scan_timestamp: '2024-01-15T10:30:00Z',
  total_resources: 1,
  scanned_regions: ['us-east-1'],
  failures: [],
};

describe('ScanControls', () => {
  const onScanComplete = vi.fn();
  const onError = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders manual refresh button that is always visible (Req 9.6)', () => {
    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    const button = screen.getByTestId('manual-refresh-button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Scan');
  });

  it('shows scanning indicator while scan is in progress (Req 9.5)', async () => {
    // Make post return a pending promise
    let resolvePost!: (value: unknown) => void;
    vi.mocked(apiClient.post).mockImplementation(() => new Promise(r => { resolvePost = r; }));

    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    // Click manual refresh
    fireEvent.click(screen.getByTestId('manual-refresh-button'));

    // Wait for spinner to appear
    await waitFor(() => {
      expect(screen.getByTestId('scan-spinner')).toBeInTheDocument();
    });
    expect(screen.getByTestId('manual-refresh-button')).toHaveTextContent('Scanning…');

    // Resolve to clean up
    vi.mocked(apiClient.get).mockResolvedValue(mockDiagramData);
    await act(async () => {
      resolvePost({});
    });
  });

  it('calls onScanComplete with diagram data on successful scan', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({});
    vi.mocked(apiClient.get).mockResolvedValue(mockDiagramData);

    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    fireEvent.click(screen.getByTestId('manual-refresh-button'));

    await waitFor(() => {
      expect(onScanComplete).toHaveBeenCalledWith(mockDiagramData);
    });
  });

  it('calls onError on scan failure without clearing diagram (Req 9.4)', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError(500, {
        error_code: 'INTERNAL_ERROR',
        message: 'Scan failed',
        details: null,
        timestamp: '2024-01-15T10:30:00Z',
        recoverable: true,
      })
    );

    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    fireEvent.click(screen.getByTestId('manual-refresh-button'));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith('Scan failed');
    });
    expect(onScanComplete).not.toHaveBeenCalled();
  });

  it('silently ignores 409 SCAN_IN_PROGRESS response (Req 9.3)', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(
      new ApiError(409, {
        error_code: 'SCAN_IN_PROGRESS',
        message: 'A scan is already in progress',
        details: null,
        timestamp: '2024-01-15T10:30:00Z',
        recoverable: true,
      })
    );

    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    fireEvent.click(screen.getByTestId('manual-refresh-button'));

    // Wait for button to return to idle
    await waitFor(() => {
      expect(screen.getByTestId('manual-refresh-button')).toHaveTextContent('Scan');
    });

    expect(onError).not.toHaveBeenCalled();
    expect(onScanComplete).not.toHaveBeenCalled();
  });

  it('does not set up timer when interval is manual (Req 9.1)', () => {
    vi.useFakeTimers();

    render(
      <ScanControls
        autoRefreshInterval="manual"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    vi.advanceTimersByTime(300_000);

    expect(apiClient.post).not.toHaveBeenCalled();

    vi.useRealTimers();
  });

  it('triggers auto-refresh at the configured interval (Req 9.1, 9.2)', async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockResolvedValue({});
    vi.mocked(apiClient.get).mockResolvedValue(mockDiagramData);

    render(
      <ScanControls
        autoRefreshInterval="1m"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    // No scan yet
    expect(apiClient.post).not.toHaveBeenCalled();

    // Advance to 1 minute and flush microtasks
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(apiClient.post).toHaveBeenCalledWith('/scan');

    vi.useRealTimers();
  });

  it('resets timer on manual refresh (Req 9.7)', async () => {
    vi.useFakeTimers();
    vi.mocked(apiClient.post).mockResolvedValue({});
    vi.mocked(apiClient.get).mockResolvedValue(mockDiagramData);

    render(
      <ScanControls
        autoRefreshInterval="5m"
        onScanComplete={onScanComplete}
        onError={onError}
      />
    );

    // Advance 4 minutes (almost triggers auto-refresh at 5m)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(240_000);
    });

    expect(apiClient.post).not.toHaveBeenCalled();

    // Manual refresh at 4 minutes resets timer
    await act(async () => {
      fireEvent.click(screen.getByTestId('manual-refresh-button'));
      await vi.advanceTimersByTimeAsync(0);
    });

    // Manual refresh should have triggered one scan
    expect(apiClient.post).toHaveBeenCalledTimes(1);

    vi.mocked(apiClient.post).mockClear();
    vi.mocked(apiClient.get).mockClear();
    vi.mocked(apiClient.post).mockResolvedValue({});
    vi.mocked(apiClient.get).mockResolvedValue(mockDiagramData);

    // Advance 1 more minute — old timer would have fired at 5m total from mount,
    // but the reset means it won't fire until 5m from the manual refresh
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(apiClient.post).not.toHaveBeenCalled();

    // Advance remaining 4m to complete the 5m from manual refresh
    await act(async () => {
      await vi.advanceTimersByTimeAsync(240_000);
    });

    expect(apiClient.post).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });
});
