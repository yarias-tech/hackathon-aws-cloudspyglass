import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError } from '../api/apiClient';
import type { CredentialSubmission, CredentialStatus } from '../types/credentials';
import type { AppSettings, AutoRefreshInterval } from '../types/settings';

const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'af-south-1', 'ap-east-1', 'ap-south-1', 'ap-south-2',
  'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3',
  'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
  'ca-central-1',
  'eu-central-1', 'eu-central-2', 'eu-west-1', 'eu-west-2', 'eu-west-3',
  'eu-south-1', 'eu-south-2', 'eu-north-1',
  'me-south-1', 'me-central-1',
  'sa-east-1',
];

const AUTO_REFRESH_OPTIONS: { value: AutoRefreshInterval; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: '1m', label: '1 minute' },
  { value: '5m', label: '5 minutes' },
  { value: '15m', label: '15 minutes' },
  { value: '30m', label: '30 minutes' },
  { value: '60m', label: '60 minutes' },
];

/**
 * SettingsPage provides credential management, region selection,
 * and auto-refresh interval configuration.
 *
 * Requirements: 1.1, 2.2, 2.5, 2.6, 3.1, 12.1, 12.3, 12.4, 12.5
 */
export function SettingsPage() {
  // Credential form state
  const [accessKeyId, setAccessKeyId] = useState('');
  const [secretAccessKey, setSecretAccessKey] = useState('');
  const [sessionToken, setSessionToken] = useState('');
  const [defaultRegion, setDefaultRegion] = useState('us-east-1');

  // Credential status state
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Form submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Disconnect state
  const [disconnecting, setDisconnecting] = useState(false);

  // Settings state
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  // Fetch credential status on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchStatus() {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const status = await apiClient.get<CredentialStatus>('/credentials/status');
        if (!cancelled) {
          setCredentialStatus(status);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setStatusError(err.message);
          } else {
            setStatusError('Failed to load credential status');
          }
        }
      } finally {
        if (!cancelled) {
          setStatusLoading(false);
        }
      }
    }

    fetchStatus();
    return () => { cancelled = true; };
  }, []);

  // Fetch settings on mount
  useEffect(() => {
    let cancelled = false;

    async function fetchSettings() {
      setSettingsLoading(true);
      setSettingsError(null);
      try {
        const appSettings = await apiClient.get<AppSettings>('/settings');
        if (!cancelled) {
          setSettings(appSettings);
        }
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError) {
            setSettingsError(err.message);
          } else {
            setSettingsError('Failed to load settings');
          }
        }
      } finally {
        if (!cancelled) {
          setSettingsLoading(false);
        }
      }
    }

    fetchSettings();
    return () => { cancelled = true; };
  }, []);

  // Handle credential submission
  const handleSubmitCredentials = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);

    const submission: CredentialSubmission = {
      access_key_id: accessKeyId,
      secret_access_key: secretAccessKey,
      session_token: sessionToken || null,
      region: defaultRegion,
    };

    try {
      const status = await apiClient.post<CredentialStatus>('/credentials', submission);
      setCredentialStatus(status);
      // Clear form on success
      setAccessKeyId('');
      setSecretAccessKey('');
      setSessionToken('');
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to submit credentials');
      }
    } finally {
      setSubmitting(false);
    }
  }, [accessKeyId, secretAccessKey, sessionToken, defaultRegion]);

  // Handle disconnect
  const handleDisconnect = useCallback(async () => {
    setDisconnecting(true);
    try {
      const status = await apiClient.delete<CredentialStatus>('/credentials');
      setCredentialStatus(status);
    } catch (err) {
      // Even on error, try to reflect disconnected state
      if (err instanceof ApiError) {
        setStatusError(err.message);
      }
    } finally {
      setDisconnecting(false);
    }
  }, []);

  // Handle auto-refresh interval change
  const handleAutoRefreshChange = useCallback(async (interval: AutoRefreshInterval) => {
    if (!settings) return;

    const newSettings: AppSettings = {
      ...settings,
      auto_refresh_interval: interval,
    };

    try {
      const updated = await apiClient.put<AppSettings>('/settings', newSettings);
      setSettings(updated);
    } catch (err) {
      if (err instanceof ApiError) {
        setSettingsError(err.message);
      }
    }
  }, [settings]);

  // Handle region selection toggle
  const handleRegionToggle = useCallback(async (region: string) => {
    if (!settings) return;

    const selectedRegions = settings.selected_regions.includes(region)
      ? settings.selected_regions.filter(r => r !== region)
      : [...settings.selected_regions, region];

    const newSettings: AppSettings = {
      ...settings,
      selected_regions: selectedRegions,
    };

    try {
      const updated = await apiClient.put<AppSettings>('/settings', newSettings);
      setSettings(updated);
    } catch (err) {
      if (err instanceof ApiError) {
        setSettingsError(err.message);
      }
    }
  }, [settings]);

  // Determine if submit button should be disabled
  const isSubmitDisabled = submitting || !accessKeyId.trim() || !secretAccessKey.trim();

  // Determine credential status display values
  const statusText = credentialStatus?.status ?? 'Disconnected';
  const statusColor = statusText === 'Connected'
    ? '#16a34a'
    : statusText === 'Expired'
      ? '#d97706'
      : '#dc2626';

  const isConnected = credentialStatus?.connected === true;

  return (
    <div style={{ maxWidth: '48rem', margin: '0 auto', padding: '2rem 1rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#111827', marginBottom: '2rem' }}>
        Settings
      </h1>

      {/* Credential Status Section */}
      <section style={{ marginBottom: '2rem', padding: '1.5rem', border: '1px solid #e5e7eb', borderRadius: '0.5rem', backgroundColor: '#fff' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '1rem' }}>
          Credential Status
        </h2>

        {statusLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }} aria-label="Loading credential status">
            <div style={{
              width: '1rem',
              height: '1rem',
              border: '2px solid #e5e7eb',
              borderTopColor: '#2563eb',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }} />
            <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>Loading status…</span>
          </div>
        ) : statusError ? (
          <p style={{ color: '#dc2626', fontSize: '0.875rem', margin: 0 }}>{statusError}</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{
                display: 'inline-block',
                width: '0.5rem',
                height: '0.5rem',
                borderRadius: '50%',
                backgroundColor: statusColor,
              }} />
              <span style={{ fontWeight: 500, color: statusColor }} data-testid="credential-status">
                {statusText}
              </span>
            </div>

            {credentialStatus?.account_id && (
              <div style={{ fontSize: '0.875rem', color: '#374151' }}>
                <span style={{ fontWeight: 500 }}>Account ID: </span>
                <span data-testid="account-id">{credentialStatus.account_id}</span>
              </div>
            )}

            {credentialStatus?.credential_source && (
              <div style={{ fontSize: '0.875rem', color: '#374151' }}>
                <span style={{ fontWeight: 500 }}>Source: </span>
                <span data-testid="credential-source">
                  {credentialStatus.credential_source === 'ui' ? 'UI-provided' : 'boto3 chain'}
                </span>
              </div>
            )}

            {isConnected && (
              <div style={{ fontSize: '0.875rem', color: '#374151' }}>
                <span style={{ fontWeight: 500 }}>Expiry: </span>
                <span data-testid="credential-expiry">
                  {credentialStatus?.expiry ?? 'No expiration'}
                </span>
              </div>
            )}

            <div style={{ marginTop: '0.75rem' }}>
              <button
                type="button"
                onClick={handleDisconnect}
                disabled={!isConnected || disconnecting}
                style={{
                  padding: '0.375rem 0.75rem',
                  backgroundColor: !isConnected || disconnecting ? '#f3f4f6' : '#fef2f2',
                  color: !isConnected || disconnecting ? '#9ca3af' : '#dc2626',
                  border: `1px solid ${!isConnected || disconnecting ? '#d1d5db' : '#fecaca'}`,
                  borderRadius: '0.375rem',
                  cursor: !isConnected || disconnecting ? 'not-allowed' : 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: 500,
                }}
                aria-label="Disconnect credentials"
                data-testid="disconnect-button"
              >
                {disconnecting ? 'Disconnecting…' : 'Disconnect'}
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Credential Form Section */}
      <section style={{ marginBottom: '2rem', padding: '1.5rem', border: '1px solid #e5e7eb', borderRadius: '0.5rem', backgroundColor: '#fff' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '1rem' }}>
          AWS Credentials
        </h2>

        <form onSubmit={handleSubmitCredentials} aria-label="Credential form">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Access Key ID */}
            <div>
              <label htmlFor="access-key-id" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#374151', marginBottom: '0.25rem' }}>
                Access Key ID
              </label>
              <input
                id="access-key-id"
                type="text"
                value={accessKeyId}
                onChange={(e) => setAccessKeyId(e.target.value)}
                maxLength={128}
                placeholder="AKIAIOSFODNN7EXAMPLE"
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '0.375rem',
                  fontSize: '0.875rem',
                  boxSizing: 'border-box',
                }}
                data-testid="access-key-input"
              />
            </div>

            {/* Secret Access Key */}
            <div>
              <label htmlFor="secret-access-key" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#374151', marginBottom: '0.25rem' }}>
                Secret Access Key
              </label>
              <input
                id="secret-access-key"
                type="password"
                value={secretAccessKey}
                onChange={(e) => setSecretAccessKey(e.target.value)}
                maxLength={128}
                placeholder="••••••••••••••••"
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '0.375rem',
                  fontSize: '0.875rem',
                  boxSizing: 'border-box',
                }}
                data-testid="secret-key-input"
              />
            </div>

            {/* Session Token (optional) */}
            <div>
              <label htmlFor="session-token" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#374151', marginBottom: '0.25rem' }}>
                Session Token <span style={{ color: '#6b7280', fontWeight: 400 }}>(optional)</span>
              </label>
              <input
                id="session-token"
                type="password"
                value={sessionToken}
                onChange={(e) => setSessionToken(e.target.value)}
                maxLength={1024}
                placeholder="••••••••••••••••"
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '0.375rem',
                  fontSize: '0.875rem',
                  boxSizing: 'border-box',
                }}
                data-testid="session-token-input"
              />
            </div>

            {/* Default Region */}
            <div>
              <label htmlFor="default-region" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#374151', marginBottom: '0.25rem' }}>
                Default Region
              </label>
              <select
                id="default-region"
                value={defaultRegion}
                onChange={(e) => setDefaultRegion(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.5rem 0.75rem',
                  border: '1px solid #d1d5db',
                  borderRadius: '0.375rem',
                  fontSize: '0.875rem',
                  backgroundColor: '#fff',
                  boxSizing: 'border-box',
                }}
                data-testid="default-region-select"
              >
                {AWS_REGIONS.map(region => (
                  <option key={region} value={region}>{region}</option>
                ))}
              </select>
            </div>

            {/* Submit error */}
            {submitError && (
              <p style={{ color: '#dc2626', fontSize: '0.875rem', margin: 0 }} role="alert" data-testid="submit-error">
                {submitError}
              </p>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isSubmitDisabled}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: isSubmitDisabled ? '#93c5fd' : '#2563eb',
                color: '#fff',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: isSubmitDisabled ? 'not-allowed' : 'pointer',
                fontSize: '0.875rem',
                fontWeight: 500,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
              }}
              data-testid="submit-credentials-button"
            >
              {submitting && (
                <div style={{
                  width: '0.875rem',
                  height: '0.875rem',
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: '#fff',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite',
                }} aria-label="Validating credentials" />
              )}
              {submitting ? 'Validating…' : 'Connect'}
            </button>
          </div>
        </form>
      </section>

      {/* Region Selector Section */}
      <section style={{ marginBottom: '2rem', padding: '1.5rem', border: '1px solid #e5e7eb', borderRadius: '0.5rem', backgroundColor: '#fff' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '0.5rem' }}>
          Scan Regions
        </h2>
        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: 0, marginBottom: '1rem' }}>
          Select one or more AWS regions to include in scans.
        </p>

        {settingsLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }} aria-label="Loading regions">
            <div style={{
              width: '1rem',
              height: '1rem',
              border: '2px solid #e5e7eb',
              borderTopColor: '#2563eb',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }} />
            <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>Loading…</span>
          </div>
        ) : settingsError ? (
          <p style={{ color: '#dc2626', fontSize: '0.875rem', margin: 0 }}>{settingsError}</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }} data-testid="region-selector">
            {AWS_REGIONS.map(region => {
              const isSelected = settings?.selected_regions.includes(region) ?? false;
              return (
                <button
                  key={region}
                  type="button"
                  onClick={() => handleRegionToggle(region)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    fontSize: '0.75rem',
                    border: `1px solid ${isSelected ? '#2563eb' : '#d1d5db'}`,
                    borderRadius: '0.25rem',
                    backgroundColor: isSelected ? '#eff6ff' : '#fff',
                    color: isSelected ? '#2563eb' : '#374151',
                    cursor: 'pointer',
                    fontWeight: isSelected ? 500 : 400,
                  }}
                  aria-pressed={isSelected}
                  aria-label={`${region} region`}
                >
                  {region}
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* Auto-Refresh Interval Section */}
      <section style={{ marginBottom: '2rem', padding: '1.5rem', border: '1px solid #e5e7eb', borderRadius: '0.5rem', backgroundColor: '#fff' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#111827', marginTop: 0, marginBottom: '0.5rem' }}>
          Auto-Refresh Interval
        </h2>
        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: 0, marginBottom: '1rem' }}>
          How often the diagram should automatically rescan for changes.
        </p>

        {settingsLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }} aria-label="Loading auto-refresh settings">
            <div style={{
              width: '1rem',
              height: '1rem',
              border: '2px solid #e5e7eb',
              borderTopColor: '#2563eb',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }} />
            <span style={{ color: '#6b7280', fontSize: '0.875rem' }}>Loading…</span>
          </div>
        ) : settingsError ? (
          <p style={{ color: '#dc2626', fontSize: '0.875rem', margin: 0 }}>{settingsError}</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }} data-testid="auto-refresh-selector">
            {AUTO_REFRESH_OPTIONS.map(option => {
              const isSelected = settings?.auto_refresh_interval === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => handleAutoRefreshChange(option.value)}
                  style={{
                    padding: '0.375rem 0.75rem',
                    fontSize: '0.875rem',
                    border: `1px solid ${isSelected ? '#2563eb' : '#d1d5db'}`,
                    borderRadius: '0.375rem',
                    backgroundColor: isSelected ? '#eff6ff' : '#fff',
                    color: isSelected ? '#2563eb' : '#374151',
                    cursor: 'pointer',
                    fontWeight: isSelected ? 500 : 400,
                  }}
                  aria-pressed={isSelected}
                  aria-label={`Auto-refresh ${option.label}`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
