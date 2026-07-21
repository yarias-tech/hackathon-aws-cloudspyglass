import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TagFilterInput } from './TagFilterInput';

// Mock the apiClient module
vi.mock('../api/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from '../api/apiClient';

describe('TagFilterInput', () => {
  const mockOnFiltersChange = vi.fn();

  beforeEach(() => {
    mockOnFiltersChange.mockClear();
    (apiClient.get as ReturnType<typeof vi.fn>).mockClear();
  });

  describe('Rendering (Requirement 7.1)', () => {
    it('renders key and value inputs when under max filters', () => {
      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );
      expect(screen.getByLabelText('Tag key')).toBeInTheDocument();
      expect(screen.getByLabelText('Tag value')).toBeInTheDocument();
    });

    it('renders the add button', () => {
      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );
      expect(screen.getByLabelText('Add tag filter')).toBeInTheDocument();
    });

    it('displays applied filter pills', () => {
      const filters = [
        { key: 'Environment', value: 'production' },
        { key: 'Team', value: 'platform' },
      ];
      render(
        <TagFilterInput filters={filters} onFiltersChange={mockOnFiltersChange} />
      );
      expect(screen.getByLabelText('Remove filter Environment=production')).toBeInTheDocument();
      expect(screen.getByLabelText('Remove filter Team=platform')).toBeInTheDocument();
    });

    it('hides input row when max filters (10) reached', () => {
      const filters = Array.from({ length: 10 }, (_, i) => ({
        key: `key${i}`,
        value: `value${i}`,
      }));
      render(
        <TagFilterInput filters={filters} onFiltersChange={mockOnFiltersChange} />
      );
      expect(screen.queryByLabelText('Tag key')).not.toBeInTheDocument();
    });

    it('shows filter count indicator', () => {
      const filters = [{ key: 'Env', value: 'prod' }];
      render(
        <TagFilterInput filters={filters} onFiltersChange={mockOnFiltersChange} />
      );
      expect(screen.getByText('(1/10)')).toBeInTheDocument();
    });
  });

  describe('Adding filters', () => {
    it('adds a filter when Add button is clicked with valid input', () => {
      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );
      fireEvent.change(screen.getByLabelText('Tag key'), {
        target: { value: 'Environment' },
      });
      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'production' },
      });
      fireEvent.click(screen.getByLabelText('Add tag filter'));

      expect(mockOnFiltersChange).toHaveBeenCalledWith([
        { key: 'Environment', value: 'production' },
      ]);
    });

    it('adds a filter on Enter key press', () => {
      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );
      fireEvent.change(screen.getByLabelText('Tag key'), {
        target: { value: 'Team' },
      });
      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'backend' },
      });
      fireEvent.keyDown(screen.getByLabelText('Tag value'), { key: 'Enter' });

      expect(mockOnFiltersChange).toHaveBeenCalledWith([
        { key: 'Team', value: 'backend' },
      ]);
    });

    it('does not add filter when key is empty', () => {
      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );
      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'production' },
      });
      fireEvent.click(screen.getByLabelText('Add tag filter'));
      expect(mockOnFiltersChange).not.toHaveBeenCalled();
    });

    it('does not add duplicate filters', () => {
      const existing = [{ key: 'Env', value: 'prod' }];
      render(
        <TagFilterInput filters={existing} onFiltersChange={mockOnFiltersChange} />
      );
      fireEvent.change(screen.getByLabelText('Tag key'), {
        target: { value: 'Env' },
      });
      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'prod' },
      });
      fireEvent.click(screen.getByLabelText('Add tag filter'));
      expect(mockOnFiltersChange).not.toHaveBeenCalled();
    });
  });

  describe('Removing filters', () => {
    it('removes a filter when × button is clicked', () => {
      const filters = [
        { key: 'Env', value: 'prod' },
        { key: 'Team', value: 'platform' },
      ];
      render(
        <TagFilterInput filters={filters} onFiltersChange={mockOnFiltersChange} />
      );
      fireEvent.click(screen.getByLabelText('Remove filter Env=prod'));
      expect(mockOnFiltersChange).toHaveBeenCalledWith([
        { key: 'Team', value: 'platform' },
      ]);
    });
  });

  describe('Autocomplete (Requirement 7.2)', () => {
    it('fetches suggestions after debounce delay', async () => {
      vi.useRealTimers();
      const mockSuggestions = [
        { key: 'Environment', value: 'production', count: 15 },
        { key: 'Environment', value: 'staging', count: 8 },
      ];
      (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockSuggestions);

      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );

      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'prod' },
      });

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith('/tags/suggestions?prefix=prod');
      });
    });

    it('displays suggestions in dropdown', async () => {
      vi.useRealTimers();
      const mockSuggestions = [
        { key: 'Environment', value: 'production', count: 15 },
      ];
      (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockSuggestions);

      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );

      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'prod' },
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      expect(screen.getByText('(15)')).toBeInTheDocument();
    });

    it('fills inputs when suggestion is clicked', async () => {
      vi.useRealTimers();
      const mockSuggestions = [
        { key: 'Environment', value: 'production', count: 15 },
      ];
      (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue(mockSuggestions);

      render(
        <TagFilterInput filters={[]} onFiltersChange={mockOnFiltersChange} />
      );

      fireEvent.change(screen.getByLabelText('Tag value'), {
        target: { value: 'prod' },
      });

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument();
      });

      const option = screen.getByRole('option');
      fireEvent.click(option);

      expect(screen.getByLabelText('Tag key')).toHaveValue('Environment');
      expect(screen.getByLabelText('Tag value')).toHaveValue('production');
    });
  });
});
