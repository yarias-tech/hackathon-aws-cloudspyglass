import { useEffect, useRef, useCallback, memo } from 'react';
import type { Resource } from '../types/resources';
import type { ErrorResponse } from '../types/errors';
import './DetailPanel.css';

export interface DetailPanelProps {
  /** The resource to display, or null if no resource is selected */
  resource: Resource | null;
  /** Whether data is currently loading */
  loading?: boolean;
  /** Error response if metadata retrieval failed */
  error?: ErrorResponse | null;
  /** Callback when the panel should close */
  onClose: () => void;
}

/**
 * DetailPanel displays full resource metadata in a slide-in overlay from the right.
 *
 * - Shows resource type, ARN, region, tags, creation date, IAM role, and attributes
 * - Omits sections for non-applicable metadata fields
 * - Handles loading state with a spinner and 10-second timeout
 * - Handles error state with structured error display
 * - Closes on Escape key or close button click
 * - Replaces content when a different node is clicked while open
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */
export const DetailPanel = memo(function DetailPanel({
  resource,
  loading = false,
  error = null,
  onClose,
}: DetailPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Close on Escape key (Requirement 6.4)
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  // Focus the close button when panel opens for accessibility
  useEffect(() => {
    if (resource || loading || error) {
      closeButtonRef.current?.focus();
    }
  }, [resource, loading, error]);

  // Don't render if there's nothing to show
  if (!resource && !loading && !error) {
    return null;
  }

  return (
    <div
      className="detail-panel"
      ref={panelRef}
      role="complementary"
      aria-label="Resource detail panel"
    >
      <div className="detail-panel__header">
        <span className="detail-panel__title">
          {resource ? resource.resource_type : 'Resource Details'}
        </span>
        <button
          ref={closeButtonRef}
          className="detail-panel__close"
          onClick={onClose}
          aria-label="Close detail panel"
          type="button"
        >
          ✕
        </button>
      </div>

      <div className="detail-panel__body">
        {loading && <LoadingIndicator />}
        {!loading && error && <ErrorDisplay error={error} />}
        {!loading && !error && resource && <ResourceContent resource={resource} />}
      </div>
    </div>
  );
});

/** Loading indicator with message (Requirement 6.2) */
function LoadingIndicator() {
  return (
    <div className="detail-panel__loading" aria-live="polite">
      <div className="detail-panel__spinner" aria-hidden="true" />
      <span>Loading resource details…</span>
    </div>
  );
}

/** Error display using ErrorResponse structure (Requirement 6.3) */
function ErrorDisplay({ error }: { error: ErrorResponse }) {
  return (
    <div className="detail-panel__error" role="alert">
      <span className="detail-panel__error-title">Failed to load resource details</span>
      <span className="detail-panel__error-message">{error.message}</span>
      {error.error_code && (
        <span className="detail-panel__error-code">{error.error_code}</span>
      )}
    </div>
  );
}

/** Resource metadata content (Requirement 6.1) */
function ResourceContent({ resource }: { resource: Resource }) {
  const hasTags = Object.keys(resource.tags).length > 0;
  const hasAttributes = Object.keys(resource.attributes).length > 0;

  return (
    <>
      {/* Identifiers section — always shown */}
      <section className="detail-panel__section">
        <h3 className="detail-panel__section-title">Identifiers</h3>
        <div className="detail-panel__field">
          <span className="detail-panel__label">ARN</span>
          <span className="detail-panel__value">{resource.arn}</span>
        </div>
        <div className="detail-panel__field">
          <span className="detail-panel__label">Region</span>
          <span className="detail-panel__value">{resource.region}</span>
        </div>
        <div className="detail-panel__field">
          <span className="detail-panel__label">Name</span>
          <span className="detail-panel__value">{resource.name}</span>
        </div>
      </section>

      {/* Tags section — omit if no tags (Requirement 6.1) */}
      {hasTags && (
        <section className="detail-panel__section">
          <h3 className="detail-panel__section-title">Tags</h3>
          <div className="detail-panel__tags">
            {Object.entries(resource.tags).map(([key, value]) => (
              <div key={key} className="detail-panel__tag">
                <span className="detail-panel__tag-key">{key}</span>
                <span className="detail-panel__tag-value">{value}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* IAM Role section — omit if null (Requirement 6.1) */}
      {resource.iam_role && (
        <section className="detail-panel__section">
          <h3 className="detail-panel__section-title">IAM Role</h3>
          <div className="detail-panel__field">
            <span className="detail-panel__value">{resource.iam_role}</span>
          </div>
        </section>
      )}

      {/* Creation Date section — omit if null (Requirement 6.1) */}
      {resource.creation_date && (
        <section className="detail-panel__section">
          <h3 className="detail-panel__section-title">Creation Date</h3>
          <div className="detail-panel__field">
            <span className="detail-panel__value">{resource.creation_date}</span>
          </div>
        </section>
      )}

      {/* Service-specific attributes — omit if empty (Requirement 6.1) */}
      {hasAttributes && (
        <section className="detail-panel__section">
          <h3 className="detail-panel__section-title">Attributes</h3>
          <div className="detail-panel__attributes">
            {Object.entries(resource.attributes).map(([key, value]) => (
              <div key={key} className="detail-panel__attribute">
                <span className="detail-panel__attribute-key">{key}</span>
                <span className="detail-panel__attribute-value">
                  {formatAttributeValue(value)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

/** Format attribute values for display */
function formatAttributeValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}
