import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SettingsPage } from './SettingsPage';
import type { CredentialStatus } from '../types/credentials';
import type { AppSettings } from '../types/settings';

// Mock the apiClient module
vi.mock('../api/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    statusCode: number;
    errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean };
    constructor(statusCode: number, errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean }) {
      super(errorResponse.message);
      this.statusCode = statusCode;
      this.errorResponse = errorResponse;
    }
  },
}));

const { apiClient } = await import('../api/apiClient');

const mockCredentialStatus: CredentialStatus = {
  connected: true,
  account_id: '123456789012',
  credential_source: 'ui',
  expiry: '2024-12-31T23:59:59Z',
  status: 'Connected',
};

const mockDisconnectedStatus: CredentialStatus = {
  connected: false,
  account_id: null,
  credential_source: null,
  expiry: null,
  status: 'Disconnected',
};

const mockSettings: AppSettings = {
  auto_refresh_interval: 'manual',
  selected_regions: ['us-east-1', 'us-west-2'],
};

function setupMocks(
  credStatus: CredentialStatus = mockCredentialStatus,
  settings: AppSettings = mockSettings,
) {
  (apiClient.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
    if (path === '/credentials/status') return Promise.resolve(credStatus);
    if (path === '/settings') return Promise.resolve(settings);
    return Promise.reject(new Error('Unknown path'));
  });
}

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    render(<SettingsPage />);
    expect(screen.getByLabelText('Loading credential status')).toBeInTheDocument();
  });

  it('displays credential status when connected', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Connected');
    });
    expect(screen.getByTestId('account-id')).toHaveTextContent('123456789012');
    expect(screen.getByTestId('credential-source')).toHaveTextContent('UI-provided');
    expect(screen.getByTestId('credential-expiry')).toHaveTextContent('2024-12-31T23:59:59Z');
  });

  it('displays "No expiration" when expiry is null and connected', async () => {
    const statusNoExpiry: CredentialStatus = {
      ...mockCredentialStatus,
      expiry: null,
    };
    setupMocks(statusNoExpiry);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-expiry')).toHaveTextContent('No expiration');
    });
  });

  it('displays disconnected status without account info', async () => {
    setupMocks(mockDisconnectedStatus);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Disconnected');
    });
    expect(screen.queryByTestId('account-id')).not.toBeInTheDocument();
    expect(screen.queryByTestId('credential-source')).not.toBeInTheDocument();
  });

  it('disables disconnect button when not connected', async () => {
    setupMocks(mockDisconnectedStatus);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('disconnect-button')).toBeDisabled();
    });
  });

  it('enables disconnect button when connected', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('disconnect-button')).not.toBeDisabled();
    });
  });

  it('clears credentials and updates status on disconnect', async () => {
    setupMocks();
    (apiClient.delete as ReturnType<typeof vi.fn>).mockResolvedValue(mockDisconnectedStatus);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Connected');
    });

    fireEvent.click(screen.getByTestId('disconnect-button'));

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Disconnected');
    });
    expect(screen.queryByTestId('account-id')).not.toBeInTheDocument();
  });

  it('disables submit button when required fields are empty', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('submit-credentials-button')).toBeDisabled();
    });
  });

  it('enables submit button when access key and secret key are filled', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('access-key-input'), { target: { value: 'AKIAIOSFODNN7EXAMPLE' } });
    fireEvent.change(screen.getByTestId('secret-key-input'), { target: { value: 'wJalrXUtnFEMI/K7MDENG' } });

    expect(screen.getByTestId('submit-credentials-button')).not.toBeDisabled();
  });

  it('submits credentials and updates status on success', async () => {
    setupMocks(mockDisconnectedStatus);
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue(mockCredentialStatus);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Disconnected');
    });

    fireEvent.change(screen.getByTestId('access-key-input'), { target: { value: 'AKIAIOSFODNN7EXAMPLE' } });
    fireEvent.change(screen.getByTestId('secret-key-input'), { target: { value: 'wJalrXUtnFEMI/K7MDENG' } });
    fireEvent.click(screen.getByTestId('submit-credentials-button'));

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toHaveTextContent('Connected');
    });
  });

  it('shows submit error when credential submission fails', async () => {
    setupMocks(mockDisconnectedStatus);
    (apiClient.post as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Invalid credentials'));
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('credential-status')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId('access-key-input'), { target: { value: 'AKIAIOSFODNN7EXAMPLE' } });
    fireEvent.change(screen.getByTestId('secret-key-input'), { target: { value: 'bad-secret' } });
    fireEvent.click(screen.getByTestId('submit-credentials-button'));

    await waitFor(() => {
      expect(screen.getByTestId('submit-error')).toHaveTextContent('Failed to submit credentials');
    });
  });

  it('renders region selector with correct selected state', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('region-selector')).toBeInTheDocument();
    });

    // us-east-1 should be pressed (selected)
    const usEast1Button = screen.getByLabelText('us-east-1 region');
    expect(usEast1Button).toHaveAttribute('aria-pressed', 'true');

    // eu-west-1 should not be pressed
    const euWest1Button = screen.getByLabelText('eu-west-1 region');
    expect(euWest1Button).toHaveAttribute('aria-pressed', 'false');
  });

  it('renders auto-refresh selector with current selection', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('auto-refresh-selector')).toBeInTheDocument();
    });

    const manualButton = screen.getByLabelText('Auto-refresh Manual');
    expect(manualButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('updates auto-refresh interval on selection', async () => {
    setupMocks();
    const updatedSettings: AppSettings = { ...mockSettings, auto_refresh_interval: '5m' };
    (apiClient.put as ReturnType<typeof vi.fn>).mockResolvedValue(updatedSettings);
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('auto-refresh-selector')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Auto-refresh 5 minutes'));

    await waitFor(() => {
      expect(apiClient.put).toHaveBeenCalledWith('/settings', expect.objectContaining({
        auto_refresh_interval: '5m',
      }));
    });
  });

  it('renders credential form fields with correct constraints', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('access-key-input')).toBeInTheDocument();
    });

    const accessKeyInput = screen.getByTestId('access-key-input') as HTMLInputElement;
    const secretKeyInput = screen.getByTestId('secret-key-input') as HTMLInputElement;
    const sessionTokenInput = screen.getByTestId('session-token-input') as HTMLInputElement;

    expect(accessKeyInput).toHaveAttribute('maxLength', '128');
    expect(secretKeyInput).toHaveAttribute('maxLength', '128');
    expect(sessionTokenInput).toHaveAttribute('maxLength', '4096');
    expect(secretKeyInput).toHaveAttribute('type', 'password');
    expect(sessionTokenInput).toHaveAttribute('type', 'password');
  });

  it('displays default region selector with all AWS regions', async () => {
    setupMocks();
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('default-region-select')).toBeInTheDocument();
    });

    const select = screen.getByTestId('default-region-select') as HTMLSelectElement;
    expect(select.options.length).toBe(26);
  });
});
