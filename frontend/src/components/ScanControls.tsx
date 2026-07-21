import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient, ApiError } from '../api/apiClient';
import type { AutoRefreshInterval } from '../types/settings';
import type { DiagramData } from '../types/diagram';

/** Convert an AutoRefreshInterval to milliseconds. Returns null for 'manual'. */
function intervalToMs(interval: AutoRefreshInterval): number | null {
  switch (interval) {
    case '1m': return 60_000;
    case '5m': return 300_000;
    case '15m': return 900_000;
    case '30m': return 1_800_000;
    case '60m': return 3_600_000;
    case 'manual': return null;
  }
}

export interface ScanControlsProps {
  /** Current auto-refresh interval from settings */
  autoRefreshInterval: AutoRefreshInterval;
  /** Callback when a scan completes successfully with new diagram data */
  onScanComplete: (data: DiagramData) => void;
  /** Callback to display an error message (non-blocking) */
  onError: (message: string) => void;
  /** Optional list of regions to scan. Empty/undefined = all regions */
  selectedRegions?: string[];
}

/**
 * ScanControls provides a manual refresh button and manages auto-refresh
 * timer logic based on the configured interval.
 *
 * - Manual refresh button is always visible (Req 9.6)
 * - Displays a non-blocking spinner while scan is in progress (Req 9.5)
 * - Skips scheduled scan if one is already in progress (Req 9.3)
 * - On failure, retains current diagram and reports error (Req 9.4)
 * - Resets timer on manual refresh (Req 9.7)
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
 */
export function ScanControls({ autoRefreshInterval, onScanComplete, onError, selectedRegions }: ScanControlsProps) {
  const [scanning, setScanning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scanningRef = useRef(false);

  // Keep scanningRef in sync with scanning state so the timer callback
  // can check the latest value without needing to re-create the interval.
  useEffect(() => {
    scanningRef.current = scanning;
  }, [scanning]);

  /**
   * Perform a scan: POST /api/scan, poll /api/scan/status until complete,
   * then GET /api/diagrams/latest on success.
   * On failure, calls onError but does NOT clear diagram data (Req 9.4).
   */
  const performScan = useCallback(async () => {
    // Skip if already scanning (Req 9.3)
    if (scanningRef.current) return;

    setScanning(true);
    try {
      // Trigger a new scan with optional region selection
      const body = selectedRegions && selectedRegions.length > 0
        ? { regions: selectedRegions }
        : {};
      await apiClient.post<unknown>('/scan', body);

      // Poll scan status until completed or failed
      let scanComplete = false;
      let attempts = 0;
      const maxAttempts = 120; // 10 minutes at 5-second intervals

      while (!scanComplete && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        attempts++;

        try {
          const status = await apiClient.get<{ status: string; error_message?: string }>('/scan/status');
          if (status.status === 'completed') {
            scanComplete = true;
          } else if (status.status === 'failed') {
            onError(status.error_message || 'Scan failed');
            return;
          }
          // If still 'in_progress', keep polling
        } catch {
          // Status check failed, keep trying
        }
      }

      if (!scanComplete) {
        onError('Scan timed out waiting for completion');
        return;
      }

      // Fetch the latest diagram data after scan completes
      const data = await apiClient.get<DiagramData>('/diagrams/latest');
      onScanComplete(data);
    } catch (err) {
      if (err instanceof ApiError) {
        // 409 SCAN_IN_PROGRESS means a scan is already running — not a real error
        if (err.statusCode === 409) {
          // Skip silently; scan is already in progress
        } else {
          onError(err.message);
        }
      } else {
        onError('Scan failed unexpectedly');
      }
    } finally {
      setScanning(false);
    }
  }, [onScanComplete, onError, selectedRegions]);

  /** Clear and restart the auto-refresh timer */
  const resetTimer = useCallback(() => {
    // Clear existing timer
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    // Set up new timer if not manual
    const ms = intervalToMs(autoRefreshInterval);
    if (ms !== null) {
      timerRef.current = setInterval(() => {
        // Skip if a scan is already in progress (Req 9.3)
        if (!scanningRef.current) {
          performScan();
        }
      }, ms);
    }
  }, [autoRefreshInterval, performScan]);

  // Set up / tear down the auto-refresh timer when interval changes (Req 9.1, 9.2)
  useEffect(() => {
    resetTimer();
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [resetTimer]);

  /** Handle manual refresh: perform scan and reset timer (Req 9.6, 9.7) */
  const handleManualRefresh = useCallback(() => {
    performScan();
    resetTimer();
  }, [performScan, resetTimer]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {/* Non-blocking refresh indicator (Req 9.5) */}
      {scanning && (
        <div
          style={{
            width: '1rem',
            height: '1rem',
            border: '2px solid #e5e7eb',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }}
          role="status"
          aria-label="Scan in progress"
          data-testid="scan-spinner"
        />
      )}

      {/* Manual refresh button — always available (Req 9.6) */}
      <button
        type="button"
        onClick={handleManualRefresh}
        disabled={scanning}
        style={{
          padding: '0.5rem 1rem',
          backgroundColor: scanning ? '#93c5fd' : '#2563eb',
          color: '#fff',
          border: 'none',
          borderRadius: '0.375rem',
          cursor: scanning ? 'not-allowed' : 'pointer',
          fontSize: '0.8rem',
          fontWeight: 500,
          display: 'flex',
          alignItems: 'center',
          gap: '0.375rem',
        }}
        aria-label="Refresh scan"
        data-testid="manual-refresh-button"
      >
        {scanning ? 'Scanning…' : 'Scan'}
      </button>
    </div>
  );
}
