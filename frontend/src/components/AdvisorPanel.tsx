import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient, ApiError } from '../api/apiClient';
import type { Pillar, Severity, Suggestion, AdvisorResponse, AdvisorStatus } from '../types/advisor';

const PILLAR_OPTIONS: { value: Pillar; label: string }[] = [
  { value: 'Security', label: 'Security' },
  { value: 'Cost_Optimization', label: 'Cost Optimization' },
  { value: 'Performance', label: 'Performance' },
];

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#ca8a04',
  low: '#2563eb',
};

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/**
 * AdvisorPanel provides AI-powered architecture analysis.
 * Allows pillar selection, triggers analysis, polls for status,
 * and displays structured suggestion results.
 *
 * Requirements: 1.3, 4.2, 4.3, 4.4, 8.1, 8.4
 */
export function AdvisorPanel() {
  const [selectedPillars, setSelectedPillars] = useState<Set<Pillar>>(
    new Set(['Security', 'Cost_Optimization', 'Performance'])
  );
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [results, setResults] = useState<AdvisorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedPillars, setExpandedPillars] = useState<Set<Pillar>>(
    new Set(['Security', 'Cost_Optimization', 'Performance'])
  );

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch initial status on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchStatus() {
      try {
        const s = await apiClient.get<AdvisorStatus>('/advisor/status');
        if (!cancelled) {
          setStatus(s);
          // If there are completed results, fetch them
          if (s.status === 'completed') {
            fetchResults();
          }
        }
      } catch (err) {
        if (!cancelled) {
          // Status endpoint may 404 if never run — that's okay
          if (err instanceof ApiError && err.statusCode === 404) {
            setStatus({ status: 'idle', task_id: null });
          }
        }
      }
    }

    fetchStatus();
    return () => { cancelled = true; };
  }, []);

  // Poll when status is in_progress
  useEffect(() => {
    if (status?.status === 'in_progress') {
      pollingRef.current = setInterval(async () => {
        try {
          const s = await apiClient.get<AdvisorStatus>('/advisor/status');
          setStatus(s);
          if (s.status === 'completed') {
            fetchResults();
          }
          if (s.status === 'completed' || s.status === 'failed') {
            stopPolling();
            setLoading(false);
            if (s.status === 'failed') {
              setError('Analysis failed. Please try again.');
            }
          }
        } catch {
          // Continue polling on transient errors
        }
      }, 2000);
    } else {
      stopPolling();
    }

    return () => { stopPolling(); };
  }, [status?.status]);

  function stopPolling() {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }

  async function fetchResults() {
    try {
      const r = await apiClient.get<AdvisorResponse>('/advisor/results');
      setResults(r);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      }
    }
  }

  const handlePillarToggle = useCallback((pillar: Pillar) => {
    setSelectedPillars(prev => {
      const next = new Set(prev);
      if (next.has(pillar)) {
        next.delete(pillar);
      } else {
        next.add(pillar);
      }
      return next;
    });
  }, []);

  const handleAnalyze = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      await apiClient.post('/advisor/analyze', {
        pillars: [...selectedPillars],
      });
      setStatus({ status: 'in_progress', task_id: null });
    } catch (err) {
      setLoading(false);
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Failed to start analysis');
      }
    }
  }, [selectedPillars]);

  const togglePillarAccordion = useCallback((pillar: Pillar) => {
    setExpandedPillars(prev => {
      const next = new Set(prev);
      if (next.has(pillar)) {
        next.delete(pillar);
      } else {
        next.add(pillar);
      }
      return next;
    });
  }, []);

  const isAnalyzeDisabled = selectedPillars.size === 0 || status?.status === 'in_progress' || loading;

  // Group suggestions by pillar
  const suggestionsByPillar: Record<Pillar, Suggestion[]> = {
    Security: [],
    Cost_Optimization: [],
    Performance: [],
  };

  if (results?.suggestions) {
    for (const suggestion of results.suggestions) {
      if (suggestionsByPillar[suggestion.pillar]) {
        suggestionsByPillar[suggestion.pillar].push(suggestion);
      }
    }
    // Sort within each pillar: by severity desc, then title asc
    for (const pillar of Object.keys(suggestionsByPillar) as Pillar[]) {
      suggestionsByPillar[pillar].sort((a, b) => {
        const sevDiff = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
        if (sevDiff !== 0) return sevDiff;
        return a.title.localeCompare(b.title);
      });
    }
  }

  return (
    <div style={{ maxWidth: '48rem', margin: '0 auto', padding: '2rem 1rem', height: '100%', overflowY: 'auto', boxSizing: 'border-box' }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#111827', marginBottom: '1.5rem' }}>
        AI Architecture Advisor
      </h2>

      {/* Pillar Selector */}
      <section style={{ marginBottom: '1.5rem', padding: '1.5rem', border: '1px solid #e5e7eb', borderRadius: '0.5rem', backgroundColor: '#fff' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '0.75rem' }}>
          Analysis Pillars
        </h3>
        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: 0, marginBottom: '1rem' }}>
          Select the pillars to include in the architecture analysis.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {PILLAR_OPTIONS.map(option => (
            <label
              key={option.value}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.875rem', color: '#374151' }}
            >
              <input
                type="checkbox"
                checked={selectedPillars.has(option.value)}
                onChange={() => handlePillarToggle(option.value)}
                style={{ width: '1rem', height: '1rem', accentColor: '#2563eb' }}
                aria-label={`${option.label} pillar`}
                data-testid={`pillar-checkbox-${option.value}`}
              />
              {option.label}
            </label>
          ))}
        </div>

        {/* Analyze Button */}
        <div style={{ marginTop: '1rem' }}>
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isAnalyzeDisabled}
            style={{
              padding: '0.5rem 1rem',
              backgroundColor: isAnalyzeDisabled ? '#93c5fd' : '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: '0.375rem',
              cursor: isAnalyzeDisabled ? 'not-allowed' : 'pointer',
              fontSize: '0.875rem',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
            data-testid="analyze-button"
            aria-label="Analyze Architecture"
          >
            {loading && (
              <div style={{
                width: '0.875rem',
                height: '0.875rem',
                border: '2px solid rgba(255,255,255,0.3)',
                borderTopColor: '#fff',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
              }} aria-label="Analysis in progress" />
            )}
            {loading ? 'Analyzing…' : 'Analyze Architecture'}
          </button>
        </div>
      </section>

      {/* Error Display */}
      {error && (
        <div
          style={{
            marginBottom: '1.5rem',
            padding: '0.75rem 1rem',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '0.375rem',
            color: '#dc2626',
            fontSize: '0.875rem',
          }}
          role="alert"
          data-testid="advisor-error"
        >
          {error}
        </div>
      )}

      {/* Status Indicator */}
      {status?.status === 'in_progress' && (
        <div style={{
          marginBottom: '1.5rem',
          padding: '0.75rem 1rem',
          backgroundColor: '#eff6ff',
          border: '1px solid #bfdbfe',
          borderRadius: '0.375rem',
          color: '#2563eb',
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }} data-testid="advisor-status-polling">
          <div style={{
            width: '0.875rem',
            height: '0.875rem',
            border: '2px solid #bfdbfe',
            borderTopColor: '#2563eb',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
          }} />
          Analysis in progress…
        </div>
      )}

      {/* Results Display */}
      {results && results.suggestions.length > 0 ? (
        <section data-testid="advisor-results">
          {(Object.keys(suggestionsByPillar) as Pillar[]).map(pillar => {
            const suggestions = suggestionsByPillar[pillar];
            if (suggestions.length === 0) return null;

            const isExpanded = expandedPillars.has(pillar);
            const pillarLabel = PILLAR_OPTIONS.find(p => p.value === pillar)?.label ?? pillar;

            return (
              <div
                key={pillar}
                style={{
                  marginBottom: '1rem',
                  border: '1px solid #e5e7eb',
                  borderRadius: '0.5rem',
                  backgroundColor: '#fff',
                  overflow: 'hidden',
                }}
              >
                {/* Accordion Header */}
                <button
                  type="button"
                  onClick={() => togglePillarAccordion(pillar)}
                  style={{
                    width: '100%',
                    padding: '1rem 1.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    backgroundColor: '#f9fafb',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                  aria-expanded={isExpanded}
                  aria-label={`${pillarLabel} suggestions`}
                  data-testid={`pillar-accordion-${pillar}`}
                >
                  <span style={{ fontSize: '0.95rem', fontWeight: 600, color: '#111827' }}>
                    {pillarLabel}
                  </span>
                  <span style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}>
                    <span style={{
                      backgroundColor: '#e5e7eb',
                      color: '#374151',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '0.125rem 0.5rem',
                      borderRadius: '9999px',
                    }} data-testid={`pillar-count-${pillar}`}>
                      {suggestions.length}
                    </span>
                    <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>
                      {isExpanded ? '▾' : '▸'}
                    </span>
                  </span>
                </button>

                {/* Accordion Content */}
                {isExpanded && (
                  <div style={{ padding: '1rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    {suggestions.map((suggestion, idx) => (
                      <SuggestionCard key={`${pillar}-${idx}`} suggestion={suggestion} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ) : !loading && !error && status?.status !== 'in_progress' ? (
        <div style={{
          padding: '2rem',
          textAlign: 'center',
          color: '#6b7280',
          fontSize: '0.875rem',
          border: '1px solid #e5e7eb',
          borderRadius: '0.5rem',
          backgroundColor: '#f9fafb',
        }} data-testid="advisor-empty-state">
          No architecture analysis has been run yet.
        </div>
      ) : null}
    </div>
  );
}

function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const severityColor = SEVERITY_COLORS[suggestion.severity];

  return (
    <div
      style={{
        padding: '1rem',
        border: '1px solid #e5e7eb',
        borderRadius: '0.375rem',
        backgroundColor: '#fff',
      }}
      data-testid="suggestion-card"
    >
      {/* Header: severity badge + title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            fontSize: '0.7rem',
            fontWeight: 600,
            textTransform: 'uppercase',
            color: severityColor,
            backgroundColor: `${severityColor}15`,
            padding: '0.125rem 0.5rem',
            borderRadius: '9999px',
            border: `1px solid ${severityColor}40`,
          }}
          data-testid="severity-badge"
        >
          <span style={{
            width: '0.4rem',
            height: '0.4rem',
            borderRadius: '50%',
            backgroundColor: severityColor,
          }} />
          {suggestion.severity}
        </span>
        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#111827' }}>
          {suggestion.title}
        </span>
      </div>

      {/* Description */}
      <p style={{ fontSize: '0.8rem', color: '#4b5563', margin: '0 0 0.75rem 0', lineHeight: 1.5 }}>
        {suggestion.description}
      </p>

      {/* Affected Resources */}
      {suggestion.affected_resources.length > 0 && (
        <div style={{ marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '0.25rem' }}>
            Affected Resources
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.125rem' }}>
            {suggestion.affected_resources.map((arn, idx) => (
              <code
                key={idx}
                style={{
                  fontSize: '0.7rem',
                  color: '#6b7280',
                  backgroundColor: '#f3f4f6',
                  padding: '0.125rem 0.375rem',
                  borderRadius: '0.25rem',
                  wordBreak: 'break-all',
                }}
              >
                {arn}
              </code>
            ))}
          </div>
        </div>
      )}

      {/* Estimated Impact (Cost_Optimization only) */}
      {suggestion.estimated_impact && (
        <div style={{ marginBottom: '0.75rem' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '0.25rem' }}>
            Estimated Impact
          </span>
          <span style={{ fontSize: '0.8rem', color: '#16a34a', fontWeight: 500 }}>
            {suggestion.estimated_impact}
          </span>
        </div>
      )}

      {/* Remediation */}
      <div>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '0.25rem' }}>
          Remediation
        </span>
        <p style={{ fontSize: '0.8rem', color: '#4b5563', margin: 0, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
          {suggestion.remediation}
        </p>
      </div>
    </div>
  );
}
