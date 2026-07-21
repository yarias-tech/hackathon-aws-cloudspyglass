import { useState, useCallback, useRef, useEffect } from 'react';
import { apiClient } from '../api/apiClient';
import type { TagFilter, TagSuggestion } from '../types/filters';

interface TagFilterInputProps {
  /** Currently applied tag filters */
  filters: TagFilter[];
  /** Callback when filters change */
  onFiltersChange: (filters: TagFilter[]) => void;
  /** Maximum number of tag filters allowed */
  maxFilters?: number;
}

/**
 * TagFilterInput provides key-value pair input with autocomplete for tag-based filtering.
 *
 * - Debounces autocomplete API calls (200ms) to /api/tags/suggestions?prefix={prefix}
 * - Displays top 20 suggestions ordered by descending frequency (Requirement 7.2)
 * - Accepts up to 10 tag key-value pairs with AND logic (Requirement 7.1)
 */
export function TagFilterInput({
  filters,
  onFiltersChange,
  maxFilters = 10,
}: TagFilterInputProps) {
  const [keyInput, setKeyInput] = useState('');
  const [valueInput, setValueInput] = useState('');
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close suggestions when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchSuggestions = useCallback(async (prefix: string) => {
    if (!prefix.trim()) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    try {
      const results = await apiClient.get<TagSuggestion[]>(
        `/tags/suggestions?prefix=${encodeURIComponent(prefix)}`
      );
      setSuggestions(results);
      setShowSuggestions(results.length > 0);
    } catch {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, []);

  const handleInputChange = useCallback(
    (field: 'key' | 'value', value: string) => {
      if (field === 'key') {
        setKeyInput(value);
      } else {
        setValueInput(value);
      }

      // Debounce autocomplete API call (200ms)
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        fetchSuggestions(value);
      }, 200);
    },
    [fetchSuggestions]
  );

  const handleAddFilter = useCallback(() => {
    const key = keyInput.trim();
    const value = valueInput.trim();
    if (!key || !value) return;
    if (filters.length >= maxFilters) return;

    // Avoid duplicates
    const isDuplicate = filters.some((f) => f.key === key && f.value === value);
    if (isDuplicate) return;

    onFiltersChange([...filters, { key, value }]);
    setKeyInput('');
    setValueInput('');
    setSuggestions([]);
    setShowSuggestions(false);
  }, [keyInput, valueInput, filters, maxFilters, onFiltersChange]);

  const handleRemoveFilter = useCallback(
    (index: number) => {
      const updated = filters.filter((_, i) => i !== index);
      onFiltersChange(updated);
    },
    [filters, onFiltersChange]
  );

  const handleSuggestionClick = useCallback(
    (suggestion: TagSuggestion) => {
      setKeyInput(suggestion.key);
      setValueInput(suggestion.value);
      setShowSuggestions(false);
    },
    []
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddFilter();
      }
    },
    [handleAddFilter]
  );

  const canAdd = keyInput.trim() && valueInput.trim() && filters.length < maxFilters;

  return (
    <div className="tag-filter-input" ref={containerRef} style={{ position: 'relative' }}>
      <div className="tag-filter-input__label" style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151', marginBottom: '0.25rem' }}>
        Tag Filters {filters.length > 0 && <span style={{ color: '#6b7280', fontWeight: 400 }}>({filters.length}/{maxFilters})</span>}
      </div>

      {/* Applied filters */}
      {filters.length > 0 && (
        <div className="tag-filter-input__pills" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginBottom: '0.5rem' }}>
          {filters.map((filter, index) => (
            <span
              key={`${filter.key}:${filter.value}-${index}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.25rem',
                padding: '0.125rem 0.5rem',
                backgroundColor: '#e0f2fe',
                color: '#0369a1',
                borderRadius: '9999px',
                fontSize: '0.75rem',
              }}
            >
              <strong>{filter.key}</strong>={filter.value}
              <button
                onClick={() => handleRemoveFilter(index)}
                aria-label={`Remove filter ${filter.key}=${filter.value}`}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '0 0.125rem',
                  color: '#0369a1',
                  fontSize: '0.875rem',
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input row */}
      {filters.length < maxFilters && (
        <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Key"
            value={keyInput}
            onChange={(e) => handleInputChange('key', e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={128}
            aria-label="Tag key"
            style={{
              flex: 1,
              padding: '0.375rem 0.5rem',
              border: '1px solid #d1d5db',
              borderRadius: '0.25rem',
              fontSize: '0.75rem',
            }}
          />
          <input
            type="text"
            placeholder="Value"
            value={valueInput}
            onChange={(e) => handleInputChange('value', e.target.value)}
            onKeyDown={handleKeyDown}
            maxLength={256}
            aria-label="Tag value"
            style={{
              flex: 1,
              padding: '0.375rem 0.5rem',
              border: '1px solid #d1d5db',
              borderRadius: '0.25rem',
              fontSize: '0.75rem',
            }}
          />
          <button
            onClick={handleAddFilter}
            disabled={!canAdd}
            aria-label="Add tag filter"
            style={{
              padding: '0.375rem 0.625rem',
              backgroundColor: canAdd ? '#2563eb' : '#d1d5db',
              color: canAdd ? '#ffffff' : '#6b7280',
              border: 'none',
              borderRadius: '0.25rem',
              cursor: canAdd ? 'pointer' : 'not-allowed',
              fontSize: '0.75rem',
              fontWeight: 500,
            }}
          >
            Add
          </button>
        </div>
      )}

      {/* Autocomplete suggestions dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <ul
          role="listbox"
          aria-label="Tag suggestions"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 10,
            maxHeight: '200px',
            overflowY: 'auto',
            backgroundColor: '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '0.25rem',
            listStyle: 'none',
            margin: '0.25rem 0 0',
            padding: '0.25rem 0',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
          }}
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={`${suggestion.key}:${suggestion.value}-${index}`}
              role="option"
              aria-selected={false}
              onClick={() => handleSuggestionClick(suggestion)}
              style={{
                padding: '0.375rem 0.75rem',
                cursor: 'pointer',
                fontSize: '0.75rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
              onMouseEnter={(e) => {
                (e.target as HTMLElement).style.backgroundColor = '#f3f4f6';
              }}
              onMouseLeave={(e) => {
                (e.target as HTMLElement).style.backgroundColor = 'transparent';
              }}
            >
              <span>
                <strong>{suggestion.key}</strong>={suggestion.value}
              </span>
              <span style={{ color: '#9ca3af', fontSize: '0.625rem' }}>
                ({suggestion.count})
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
