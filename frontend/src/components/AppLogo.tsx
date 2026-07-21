import { useState } from 'react';

/**
 * AppLogo renders the application logo loaded from the backend
 * /api/images/logo endpoint.
 *
 * Falls back to a text-based logo if the image fails to load.
 *
 * Requirements: 13.4, 13.5
 */
export function AppLogo() {
  const [loadError, setLoadError] = useState(false);

  if (loadError) {
    return (
      <span
        style={{
          fontSize: '1.1rem',
          fontWeight: 700,
          color: '#111827',
          letterSpacing: '-0.02em',
        }}
        aria-label="CloudSpyglass logo"
      >
        CloudSpyglass
      </span>
    );
  }

  return (
    <img
      src="/api/images/logo"
      alt="CloudSpyglass logo"
      onError={() => setLoadError(true)}
      style={{
        height: '2rem',
        width: 'auto',
        objectFit: 'contain',
      }}
    />
  );
}
