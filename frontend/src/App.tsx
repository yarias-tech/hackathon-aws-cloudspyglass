import { Component, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { NavHeader } from './components/NavHeader';
import { ErrorBanner } from './components/ErrorBanner';
import { DiagramPage } from './pages/DiagramPage';
import { SettingsPage } from './pages/SettingsPage';
import type { ErrorResponse } from './types/errors';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: ErrorResponse | null;
}

/**
 * Global error boundary that catches unhandled render errors
 * and displays them via ErrorBanner.
 */
class AppErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(err: unknown): ErrorBoundaryState {
    const message = err instanceof Error ? err.message : 'An unexpected error occurred';
    return {
      error: {
        error_code: 'RENDER_ERROR',
        message,
        details: err instanceof Error ? err.stack ?? null : null,
        timestamp: new Date().toISOString(),
        recoverable: true,
      },
    };
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  handleDismiss = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '1rem' }}>
          <ErrorBanner
            error={this.state.error}
            onRetry={this.handleRetry}
            onDismiss={this.handleDismiss}
          />
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
        <NavHeader />
        <AppErrorBoundary>
          <div style={{ flex: 1, overflow: 'hidden' }}>
            <Routes>
              <Route path="/" element={<DiagramPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        </AppErrorBoundary>
      </div>
    </BrowserRouter>
  );
}

export default App;
