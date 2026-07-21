import { useState, useCallback, useRef, useEffect } from 'react';
import { apiClient, ApiError } from '../api/apiClient';
import type { FilterCriteria } from '../types/filters';
import type { ExportFormat, ExportRequest, ExportResult } from '../types/export';

export interface ExportMenuProps {
  /** Current active filter criteria */
  filters: FilterCriteria;
}

/** Available export format options */
const EXPORT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'pdf', label: 'PDF' },
  { format: 'png', label: 'PNG (300 DPI)' },
  { format: 'svg', label: 'SVG' },
];

/** Check whether the given filters contain any active criteria */
function hasActiveFilters(filters: FilterCriteria): boolean {
  return filters.tag_filters.length > 0 || filters.type_filters.length > 0;
}

/**
 * ExportMenu provides a dropdown button to export the current diagram
 * in PDF, PNG, or SVG format.
 *
 * - Posts to /api/export with the selected format and current filter criteria
 * - Shows loading state while export is in progress
 * - Displays success message with filename on completion
 * - Shows error message on failure
 * - Auto-dismisses status messages after a few seconds
 *
 * Requirements: 11.1, 11.2
 */
export function ExportMenu({ filters }: ExportMenuProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const menuRef = useRef<HTMLDivElement>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }

    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [menuOpen]);

  // Cleanup dismiss timer on unmount
  useEffect(() => {
    return () => {
      if (dismissTimerRef.current !== null) {
        clearTimeout(dismissTimerRef.current);
      }
    };
  }, []);

  /** Show a status message and auto-dismiss after delay */
  const showStatus = useCallback((type: 'success' | 'error', message: string) => {
    if (dismissTimerRef.current !== null) {
      clearTimeout(dismissTimerRef.current);
    }

    if (type === 'success') {
      setSuccessMessage(message);
      setErrorMessage(null);
    } else {
      setErrorMessage(message);
      setSuccessMessage(null);
    }

    dismissTimerRef.current = setTimeout(() => {
      setSuccessMessage(null);
      setErrorMessage(null);
      dismissTimerRef.current = null;
    }, 4000);
  }, []);

  /** Handle export format selection */
  const handleExport = useCallback(async (format: ExportFormat) => {
    setMenuOpen(false);
    setExporting(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    const requestBody: ExportRequest = {
      format,
      filters: hasActiveFilters(filters) ? filters : null,
    };

    try {
      const result = await apiClient.post<ExportResult>('/export', requestBody);
      showStatus('success', `Exported: ${result.filename}`);
    } catch (err) {
      if (err instanceof ApiError) {
        showStatus('error', err.message);
      } else {
        showStatus('error', 'Export failed unexpectedly');
      }
    } finally {
      setExporting(false);
    }
  }, [filters, showStatus]);

  /** Toggle dropdown menu */
  const toggleMenu = useCallback(() => {
    if (!exporting) {
      setMenuOpen((prev) => !prev);
    }
  }, [exporting]);

  return (
    <div
      ref={menuRef}
      style={{ position: 'relative', display: 'inline-block' }}
      data-testid="export-menu"
    >
      {/* Export trigger button */}
      <button
        type="button"
        onClick={toggleMenu}
        disabled={exporting}
        style={{
          padding: '0.5rem 1rem',
          backgroundColor: exporting ? '#93c5fd' : '#2563eb',
          color: '#fff',
          border: 'none',
          borderRadius: '0.375rem',
          cursor: exporting ? 'not-allowed' : 'pointer',
          fontSize: '0.8rem',
          fontWeight: 500,
          display: 'flex',
          alignItems: 'center',
          gap: '0.375rem',
        }}
        aria-label="Export menu"
        aria-expanded={menuOpen}
        aria-haspopup="true"
        data-testid="export-menu-button"
      >
        {exporting ? 'Exporting…' : 'Export ▾'}
      </button>

      {/* Dropdown menu */}
      {menuOpen && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: '0.25rem',
            backgroundColor: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '0.375rem',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            zIndex: 50,
            minWidth: '140px',
            overflow: 'hidden',
          }}
          role="menu"
          aria-label="Export format options"
          data-testid="export-menu-dropdown"
        >
          {EXPORT_FORMATS.map(({ format, label }) => (
            <button
              key={format}
              type="button"
              role="menuitem"
              onClick={() => handleExport(format)}
              style={{
                display: 'block',
                width: '100%',
                padding: '0.5rem 1rem',
                backgroundColor: 'transparent',
                border: 'none',
                textAlign: 'left',
                cursor: 'pointer',
                fontSize: '0.8rem',
                color: '#374151',
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLButtonElement).style.backgroundColor = '#f3f4f6';
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLButtonElement).style.backgroundColor = 'transparent';
              }}
              aria-label={`Export as ${label}`}
              data-testid={`export-option-${format}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Status messages */}
      {successMessage && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: '0.25rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#ecfdf5',
            border: '1px solid #a7f3d0',
            borderRadius: '0.375rem',
            color: '#065f46',
            fontSize: '0.75rem',
            whiteSpace: 'nowrap',
            zIndex: 50,
          }}
          role="status"
          aria-live="polite"
          data-testid="export-success-message"
        >
          {successMessage}
        </div>
      )}

      {errorMessage && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            marginTop: '0.25rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '0.375rem',
            color: '#dc2626',
            fontSize: '0.75rem',
            whiteSpace: 'nowrap',
            zIndex: 50,
          }}
          role="alert"
          aria-live="assertive"
          data-testid="export-error-message"
        >
          {errorMessage}
        </div>
      )}
    </div>
  );
}
