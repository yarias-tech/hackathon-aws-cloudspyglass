import { useState } from 'react';
import type { ErrorResponse } from '../types/errors';

export interface ErrorBannerProps {
  error: ErrorResponse;
  onDismiss?: () => void;
  onRetry?: () => void;
}

/**
 * ErrorBanner displays global error messages.
 *
 * - Recoverable errors show as dismissible warning banners with an optional "Retry" button.
 * - Non-recoverable errors show as persistent error banners requiring user action.
 *
 * Requirements: 14.1, 14.2, 14.3
 */
export function ErrorBanner({ error, onDismiss, onRetry }: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) {
    return null;
  }

  const isRecoverable = error.recoverable;

  const bannerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    borderRadius: '0.375rem',
    fontSize: '0.875rem',
    lineHeight: '1.25rem',
    backgroundColor: isRecoverable ? '#fef3c7' : '#fee2e2',
    border: `1px solid ${isRecoverable ? '#f59e0b' : '#ef4444'}`,
    color: isRecoverable ? '#92400e' : '#991b1b',
  };

  const handleDismiss = () => {
    setDismissed(true);
    onDismiss?.();
  };

  return (
    <div role="alert" aria-live="assertive" style={bannerStyle}>
      <span style={{ fontWeight: 500 }} aria-hidden="true">
        {isRecoverable ? '⚠' : '✕'}
      </span>

      <div style={{ flex: 1 }}>
        <p style={{ margin: 0, fontWeight: 500 }}>{error.message}</p>
        {error.details && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', opacity: 0.85 }}>
            {error.details}
          </p>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
        {isRecoverable && onRetry && (
          <button
            onClick={onRetry}
            style={{
              padding: '0.25rem 0.5rem',
              fontSize: '0.8125rem',
              fontWeight: 500,
              color: '#92400e',
              backgroundColor: '#fde68a',
              border: '1px solid #f59e0b',
              borderRadius: '0.25rem',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        )}
        {isRecoverable && (
          <button
            onClick={handleDismiss}
            aria-label="Dismiss error"
            style={{
              padding: '0.25rem',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'inherit',
              fontSize: '1rem',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
