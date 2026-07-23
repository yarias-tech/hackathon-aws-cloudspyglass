import { useState, useCallback, useRef, useEffect } from 'react';
import type { ExportFormat } from '../types/export';

export interface ExportMenuProps {
  /** Account ID for the filename */
  accountId?: string;
}

/** Available export format options */
const EXPORT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'pdf', label: 'PDF' },
  { format: 'png', label: 'PNG (300 DPI)' },
  { format: 'svg', label: 'SVG' },
];

/**
 * Generate a timestamped export filename.
 */
function generateFilename(accountId: string, format: ExportFormat): string {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[-:T]/g, '').slice(0, 15).replace(/(\d{8})(\d{6})/, '$1_$2');
  return `${accountId}_${timestamp}.${format}`;
}

/**
 * Trigger a browser download from a Blob.
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/**
 * ExportMenu provides a dropdown button to export the current diagram
 * in PDF, PNG, or SVG format by capturing the React Flow canvas directly.
 *
 * This produces an export that matches exactly what the user sees on screen,
 * including AWS icons, layout, colors, and edges.
 *
 * Requirements: 11.1, 11.2
 */
export function ExportMenu({ accountId = 'export' }: ExportMenuProps) {
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

  /** Handle export format selection — captures the React Flow canvas */
  const handleExport = useCallback(async (format: ExportFormat) => {
    setMenuOpen(false);
    setExporting(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    try {
      // Find the React Flow viewport element
      const flowElement = document.querySelector('.react-flow') as HTMLElement | null;
      if (!flowElement) {
        throw new Error('Diagram not found. Please ensure a diagram is displayed.');
      }

      const filename = generateFilename(accountId, format);

      if (format === 'svg') {
        await exportAsSvg(flowElement, filename);
      } else if (format === 'png') {
        await exportAsPng(flowElement, filename);
      } else if (format === 'pdf') {
        await exportAsPdf(flowElement, filename);
      }

      showStatus('success', `Exported: ${filename}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Export failed unexpectedly';
      showStatus('error', message);
    } finally {
      setExporting(false);
    }
  }, [accountId, showStatus]);

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

// -------------------------------------------------------------------
// Export helpers — capture the React Flow canvas using html2canvas/jspdf
// -------------------------------------------------------------------

/**
 * Export the diagram as SVG by cloning the React Flow SVG layer and
 * serializing it along with the node HTML overlays.
 */
async function exportAsSvg(flowElement: HTMLElement, filename: string): Promise<void> {
  // Use html2canvas to render to canvas, then convert to SVG-wrapped image
  const html2canvas = (await import('html2canvas')).default;

  const canvas = await html2canvas(flowElement, {
    backgroundColor: '#ffffff',
    scale: 2,
    useCORS: true,
    logging: false,
  });

  // Convert canvas to PNG data URL and embed in SVG
  const dataUrl = canvas.toDataURL('image/png');
  const svgContent = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="${canvas.width}" height="${canvas.height}"
  viewBox="0 0 ${canvas.width} ${canvas.height}">
  <image width="${canvas.width}" height="${canvas.height}" xlink:href="${dataUrl}"/>
</svg>`;

  const blob = new Blob([svgContent], { type: 'image/svg+xml' });
  downloadBlob(blob, filename);
}

/**
 * Export the diagram as PNG at high resolution using html2canvas.
 */
async function exportAsPng(flowElement: HTMLElement, filename: string): Promise<void> {
  const html2canvas = (await import('html2canvas')).default;

  // Scale 3x for ~300 DPI equivalent
  const canvas = await html2canvas(flowElement, {
    backgroundColor: '#ffffff',
    scale: 3,
    useCORS: true,
    logging: false,
  });

  canvas.toBlob((blob) => {
    if (blob) {
      downloadBlob(blob, filename);
    }
  }, 'image/png');
}

/**
 * Export the diagram as PDF using html2canvas + jsPDF.
 * Captures the canvas at high resolution and embeds it in a landscape PDF.
 */
async function exportAsPdf(flowElement: HTMLElement, filename: string): Promise<void> {
  const html2canvas = (await import('html2canvas')).default;
  const { jsPDF } = await import('jspdf');

  const canvas = await html2canvas(flowElement, {
    backgroundColor: '#ffffff',
    scale: 2,
    useCORS: true,
    logging: false,
  });

  const imgData = canvas.toDataURL('image/png');
  const imgWidth = canvas.width;
  const imgHeight = canvas.height;

  // Use landscape orientation, sized to fit the diagram
  const orientation = imgWidth >= imgHeight ? 'landscape' : 'portrait';
  const pdf = new jsPDF({
    orientation,
    unit: 'px',
    format: [imgWidth, imgHeight],
  });

  pdf.addImage(imgData, 'PNG', 0, 0, imgWidth, imgHeight);
  const pdfBlob = pdf.output('blob');
  downloadBlob(pdfBlob, filename);
}
