export interface LoadingSpinnerProps {
  /** Size of the spinner in pixels. Default: 24 */
  size?: number;
  /** Optional label shown next to the spinner for accessibility */
  label?: string;
}

/**
 * LoadingSpinner is a shared loading indicator that can be reused
 * across the application wherever async operations are in progress.
 */
export function LoadingSpinner({ size = 24, label }: LoadingSpinnerProps) {
  const spinnerStyle: React.CSSProperties = {
    width: size,
    height: size,
    border: `${Math.max(2, size / 10)}px solid #e5e7eb`,
    borderTopColor: '#2563eb',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    flexShrink: 0,
  };

  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div
        role="status"
        aria-label={label ?? 'Loading'}
        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
      >
        <div style={spinnerStyle} />
        {label && (
          <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>{label}</span>
        )}
      </div>
    </>
  );
}
