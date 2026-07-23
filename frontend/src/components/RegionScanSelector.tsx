import { useState, useRef, useEffect } from 'react';

const AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'af-south-1', 'ap-east-1', 'ap-south-1', 'ap-south-2',
  'ap-southeast-1', 'ap-southeast-2', 'ap-southeast-3',
  'ap-northeast-1', 'ap-northeast-2', 'ap-northeast-3',
  'ca-central-1', 'eu-central-1', 'eu-central-2',
  'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-north-1', 'eu-south-1',
  'me-south-1', 'me-central-1', 'sa-east-1',
];

export interface RegionScanSelectorProps {
  selectedRegions: string[];
  onChange: (regions: string[]) => void;
}

/**
 * A multi-select dropdown for choosing AWS regions to scan.
 * When empty, all regions will be scanned.
 */
export function RegionScanSelector({ selectedRegions, onChange }: RegionScanSelectorProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleRegion = (region: string) => {
    if (selectedRegions.includes(region)) {
      onChange(selectedRegions.filter(r => r !== region));
    } else {
      onChange([...selectedRegions, region]);
    }
  };

  const clearAll = () => onChange([]);

  const buttonLabel = selectedRegions.length === 0
    ? 'All Regions'
    : `${selectedRegions.length} region${selectedRegions.length > 1 ? 's' : ''}`;

  return (
    <div ref={containerRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          padding: '0.5rem 0.75rem',
          backgroundColor: '#f9fafb',
          border: '1px solid #d1d5db',
          borderRadius: '0.375rem',
          cursor: 'pointer',
          fontSize: '0.8rem',
          fontWeight: 500,
          color: '#374151',
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
        }}
        aria-label="Select regions to scan"
        data-testid="region-scan-selector"
      >
        🌍 {buttonLabel}
        <span style={{ fontSize: '0.6rem', marginLeft: '0.25rem' }}>▼</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: '0.25rem',
            backgroundColor: '#fff',
            border: '1px solid #d1d5db',
            borderRadius: '0.5rem',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            zIndex: 1000,
            width: '220px',
            maxHeight: '320px',
            overflowY: 'auto',
            padding: '0.5rem 0',
          }}
        >
          {/* Header with clear button */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.25rem 0.75rem 0.5rem',
            borderBottom: '1px solid #e5e7eb',
            marginBottom: '0.25rem',
          }}>
            <span style={{ fontSize: '0.75rem', color: '#6b7280', fontWeight: 500 }}>
              {selectedRegions.length === 0 ? 'Scanning all regions' : `${selectedRegions.length} selected`}
            </span>
            {selectedRegions.length > 0 && (
              <button
                type="button"
                onClick={clearAll}
                style={{
                  fontSize: '0.7rem',
                  color: '#2563eb',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Clear all
              </button>
            )}
          </div>

          {AWS_REGIONS.map(region => (
            <label
              key={region}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.3rem 0.75rem',
                cursor: 'pointer',
                fontSize: '0.8rem',
                color: '#374151',
                backgroundColor: selectedRegions.includes(region) ? '#eff6ff' : 'transparent',
              }}
            >
              <input
                type="checkbox"
                checked={selectedRegions.includes(region)}
                onChange={() => toggleRegion(region)}
                style={{ margin: 0 }}
              />
              {region}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
