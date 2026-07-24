import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface ScanContextValue {
  /** Last completed scan duration in seconds, null if no scan has been done */
  lastScanDuration: number | null;
  /** Update the last scan duration */
  setLastScanDuration: (seconds: number) => void;
}

const ScanContext = createContext<ScanContextValue | null>(null);

export function ScanProvider({ children }: { children: ReactNode }) {
  const [lastScanDuration, setLastScanDurationState] = useState<number | null>(null);

  const setLastScanDuration = useCallback((seconds: number) => {
    setLastScanDurationState(seconds);
  }, []);

  return (
    <ScanContext.Provider value={{ lastScanDuration, setLastScanDuration }}>
      {children}
    </ScanContext.Provider>
  );
}

export function useScanContext(): ScanContextValue {
  const context = useContext(ScanContext);
  if (!context) {
    throw new Error('useScanContext must be used within a ScanProvider');
  }
  return context;
}
