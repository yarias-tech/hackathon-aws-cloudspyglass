/**
 * EmptyState component displayed when no scan data is available.
 * Prompts the user to configure credentials and run a scan.
 */
export function EmptyState() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        padding: '2rem',
        textAlign: 'center',
        color: '#6b7280',
      }}
      role="status"
      aria-label="No scan data available"
    >
      <svg
        width="64"
        height="64"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        style={{ marginBottom: '1rem', opacity: 0.6 }}
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" />
      </svg>
      <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.25rem', color: '#374151' }}>
        No Infrastructure Diagram Available
      </h2>
      <p style={{ margin: '0 0 1.5rem', maxWidth: '400px', lineHeight: 1.6 }}>
        Configure your AWS credentials and run a scan to visualize your cloud infrastructure.
      </p>
      <a
        href="/settings"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '0.625rem 1.25rem',
          backgroundColor: '#2563eb',
          color: '#ffffff',
          borderRadius: '0.375rem',
          textDecoration: 'none',
          fontWeight: 500,
          fontSize: '0.875rem',
          transition: 'background-color 0.15s',
        }}
      >
        Configure Credentials &amp; Scan
      </a>
    </div>
  );
}
