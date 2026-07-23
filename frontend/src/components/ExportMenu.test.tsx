import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ExportMenu } from './ExportMenu';
import type { FilterCriteria } from '../types/filters';

// Mock the apiClient module
vi.mock('../api/apiClient', () => {
  const ApiError = class ApiError extends Error {
    public readonly errorResponse;
    public readonly statusCode;
    constructor(statusCode: number, errorResponse: { error_code: string; message: string; details: string | null; timestamp: string; recoverable: boolean }) {
      super(errorResponse.message);
      this.name = 'ApiError';
      this.statusCode = statusCode;
      this.errorResponse = errorResponse;
    }
    get recoverable() { return this.errorResponse.recoverable; }
    get errorCode() { return this.errorResponse.error_code; }
  };

  return {
    apiClient: {
      post: vi.fn(),
    },
    ApiError,
  };
});

import { apiClient, ApiError } from '../api/apiClient';

const emptyFilters: FilterCriteria = {
  tag_filters: [],
  type_filters: [],
};

const activeFilters: FilterCriteria = {
  tag_filters: [{ key: 'Environment', value: 'production' }],
  type_filters: ['ec2'],
};

describe('ExportMenu', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('Rendering', () => {
    it('renders an export button', () => {
      render(<ExportMenu filters={emptyFilters} />);
      expect(screen.getByTestId('export-menu-button')).toBeInTheDocument();
      expect(screen.getByTestId('export-menu-button')).toHaveTextContent('Export ▾');
    });

    it('does not show dropdown initially', () => {
      render(<ExportMenu filters={emptyFilters} />);
      expect(screen.queryByTestId('export-menu-dropdown')).not.toBeInTheDocument();
    });
  });

  describe('Dropdown menu (Requirement 11.1)', () => {
    it('opens dropdown when export button is clicked', () => {
      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));
      expect(screen.getByTestId('export-menu-dropdown')).toBeInTheDocument();
    });

    it('shows PDF, PNG, and SVG options', () => {
      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));
      expect(screen.getByTestId('export-option-pdf')).toHaveTextContent('PDF');
      expect(screen.getByTestId('export-option-png')).toHaveTextContent('PNG (300 DPI)');
      expect(screen.getByTestId('export-option-svg')).toHaveTextContent('SVG');
    });

    it('closes dropdown when clicking outside', () => {
      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));
      expect(screen.getByTestId('export-menu-dropdown')).toBeInTheDocument();

      fireEvent.mouseDown(document.body);
      expect(screen.queryByTestId('export-menu-dropdown')).not.toBeInTheDocument();
    });

    it('has correct aria attributes on the button', () => {
      render(<ExportMenu filters={emptyFilters} />);
      const button = screen.getByTestId('export-menu-button');
      expect(button).toHaveAttribute('aria-haspopup', 'true');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(button);
      expect(button).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('Export request (Requirement 11.2)', () => {
    it('sends null filters when no active filters', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({
        filename: 'diagram.pdf',
        format: 'pdf',
        size_bytes: 1024,
        path: '/exports/diagram.pdf',
      });

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(apiClient.post).toHaveBeenCalledWith('/export', {
        format: 'pdf',
        filters: null,
      });
    });

    it('sends active filters when filters are present', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({
        filename: 'diagram-filtered.png',
        format: 'png',
        size_bytes: 2048,
        path: '/exports/diagram-filtered.png',
      });

      render(<ExportMenu filters={activeFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-png'));
      });

      expect(apiClient.post).toHaveBeenCalledWith('/export', {
        format: 'png',
        filters: activeFilters,
      });
    });

    it('sends svg format when SVG option clicked', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({
        filename: 'diagram.svg',
        format: 'svg',
        size_bytes: 512,
        path: '/exports/diagram.svg',
      });

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-svg'));
      });

      expect(apiClient.post).toHaveBeenCalledWith('/export', {
        format: 'svg',
        filters: null,
      });
    });
  });

  describe('Loading state', () => {
    it('shows exporting state while request is in progress', async () => {
      let resolveExport: (value: unknown) => void;
      vi.mocked(apiClient.post).mockImplementation(() => new Promise((resolve) => { resolveExport = resolve; }));

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-menu-button')).toHaveTextContent('Exporting…');
      expect(screen.getByTestId('export-menu-button')).toBeDisabled();

      await act(async () => {
        resolveExport!({ filename: 'diagram.pdf', format: 'pdf', size_bytes: 1024, path: '/exports/diagram.pdf' });
      });

      expect(screen.getByTestId('export-menu-button')).toHaveTextContent('Export ▾');
      expect(screen.getByTestId('export-menu-button')).not.toBeDisabled();
    });
  });

  describe('Success messages', () => {
    it('displays success message with filename after export', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({
        filename: 'infrastructure-diagram.pdf',
        format: 'pdf',
        size_bytes: 4096,
        path: '/exports/infrastructure-diagram.pdf',
      });

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-success-message')).toHaveTextContent(
        'Exported: infrastructure-diagram.pdf'
      );
    });

    it('auto-dismisses success message after timeout', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({
        filename: 'diagram.pdf',
        format: 'pdf',
        size_bytes: 1024,
        path: '/exports/diagram.pdf',
      });

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-success-message')).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(4000);
      });

      expect(screen.queryByTestId('export-success-message')).not.toBeInTheDocument();
    });
  });

  describe('Error handling', () => {
    it('displays error message when ApiError occurs', async () => {
      const error = new (ApiError as unknown as new (statusCode: number, errorResponse: unknown) => Error)(500, {
        error_code: 'EXPORT_FAILED',
        message: 'Export service unavailable',
        details: null,
        timestamp: new Date().toISOString(),
        recoverable: true,
      });
      vi.mocked(apiClient.post).mockRejectedValue(error);

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-error-message')).toHaveTextContent(
        'Export service unavailable'
      );
    });

    it('displays generic error for non-ApiError exceptions', async () => {
      vi.mocked(apiClient.post).mockRejectedValue(new Error('Network error'));

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-error-message')).toHaveTextContent(
        'Export failed unexpectedly'
      );
    });

    it('auto-dismisses error message after timeout', async () => {
      vi.mocked(apiClient.post).mockRejectedValue(new Error('fail'));

      render(<ExportMenu filters={emptyFilters} />);
      fireEvent.click(screen.getByTestId('export-menu-button'));

      await act(async () => {
        fireEvent.click(screen.getByTestId('export-option-pdf'));
      });

      expect(screen.getByTestId('export-error-message')).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(4000);
      });

      expect(screen.queryByTestId('export-error-message')).not.toBeInTheDocument();
    });
  });
});
