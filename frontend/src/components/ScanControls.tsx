import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient, ApiError } from '../api/apiClient';
import { useLanguage } from '../i18n/LanguageContext';
import { useScanContext } from '../contexts/ScanContext';
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

/** Format elapsed seconds into mm:ss */
function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
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
 * - Shows elapsed time counter that persists after scan completes
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
 */
export function ScanControls({ autoRefreshInterval, onScanComplete, onError, selectedRegions }: ScanControlsProps) {
  const { t } = useLanguage();
  const { lastScanDuration, setLastScanDuration } = useScanContext();
  const [scanning, setScanning] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scanningRef = useRef(false);

  // Keep scanningRef in sync with scanning state
  useEffect(() => {
    scanningRef.current = scanning;
  }, [scanning]);

  // Elapsed time counter — starts when scanning begins, stops when it ends
  useEffect(() => {
    if (scanning) {
      setElapsedSeconds(0);
      elapsedTimerRef.current = setInterval(() => {
        setElapsedSeconds(prev => prev + 1);
      }, 1000);
    } else {
      if (elapsedTimerRef.current !== null) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
      // Save last scan duration when scanning stops (only if it actually ran)
      if (elapsedSeconds > 0) {
        setLastScanDuration(elapsedSeconds);
      }
    }

    return () => {
      if (elapsedTimerRef.current !== null) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanning]);

  /**
   * Perform a scan: POST /api/scan, poll /api/scan/status until complete,
   * then GET /api/diagrams/latest on success.
   */
  const performScan = useCallback(async () => {
    if (scanningRef.current) return;

    setScanning(true);
    try {
      const body = selectedRegions && selectedRegions.length > 0
        ? { regions: selectedRegions }
        : {};
      await apiClient.post<unknown>('/scan', body);

      let scanComplete = false;
      let attempts = 0;
      const maxAttempts = 360;

      while (!scanComplete && attempts < maxAttempts && scanningRef.current) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        attempts++;

        if (!scanningRef.current) return;

        try {
          const status = await apiClient.get<{ status: string; error_message?: string }>('/scan/status');
          if (status.status === 'completed') {
            scanComplete = true;
          } else if (status.status === 'failed') {
            onError(status.error_message || 'Scan failed');
            return;
          } else if (status.status === 'idle' && attempts > 1) {
            return;
          }
        } catch {
          // Status check failed, keep trying
        }
      }

      if (!scanComplete) {
        if (scanningRef.current) {
          onError('Scan timed out waiting for completion');
        }
        return;
      }

      const data = await apiClient.get<DiagramData>('/diagrams/latest');
      onScanComplete(data);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.statusCode !== 409) {
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
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    const ms = intervalToMs(autoRefreshInterval);
    if (ms !== null) {
      timerRef.current = setInterval(() => {
        if (!scanningRef.current) {
          performScan();
        }
      }, ms);
    }
  }, [autoRefreshInterval, performScan]);

  useEffect(() => {
    resetTimer();
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [resetTimer]);

  const handleManualRefresh = useCallback(() => {
    performScan();
    resetTimer();
  }, [performScan, resetTimer]);

  const handleCancelScan = useCallback(async () => {
    setScanning(false);
    try {
      await apiClient.post<unknown>('/scan/cancel');
    } catch {
      // Ignore errors on cancel
    }
  }, []);

  // Determine what time to show: active elapsed or last scan duration
  const displayTime = scanning ? elapsedSeconds : lastScanDuration;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {/* Non-blocking refresh indicator */}
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

      {/* Manual refresh button */}
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
        {scanning ? t.scan_scanning : t.scan_button}
      </button>

      {/* Elapsed time counter — always visible once a scan has run */}
      {displayTime !== null && (
        <span
          style={{
            fontSize: '0.75rem',
            fontWeight: 500,
            color: scanning ? '#2563eb' : '#6b7280',
            fontVariantNumeric: 'tabular-nums',
            display: 'flex',
            alignItems: 'center',
            gap: '0.25rem',
          }}
          data-testid="scan-elapsed-time"
          aria-live="polite"
        >
          ⏱ {formatElapsed(displayTime)}
        </span>
      )}

      {/* Stop button — visible only while scanning */}
      {scanning && (
        <button
          type="button"
          onClick={handleCancelScan}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: '#dc2626',
            color: '#fff',
            border: 'none',
            borderRadius: '0.375rem',
            cursor: 'pointer',
            fontSize: '0.8rem',
            fontWeight: 500,
          }}
          aria-label="Stop scan"
          data-testid="stop-scan-button"
        >
          {t.scan_stop}
        </button>
      )}
    </div>
  );
}
