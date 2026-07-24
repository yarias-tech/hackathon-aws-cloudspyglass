import { useState, useRef, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { AppLogo } from './AppLogo';
import { useLanguage } from '../i18n/LanguageContext';
import type { Language } from '../i18n/translations';

const LANGUAGE_OPTIONS: { value: Language; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
  { value: 'pt', label: 'Português' },
];

const LANGUAGE_SHORT: Record<Language, string> = {
  en: 'EN',
  es: 'ES',
  pt: 'PT',
};

/**
 * NavHeader provides the top navigation bar with:
 * - Left: App logo
 * - Right: Language dropdown, Diagram link, Settings link
 *
 * Requirements: 13.4, 13.5
 */
export function NavHeader() {
  const { language, setLanguage, t } = useLanguage();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [dropdownOpen]);

  const linkStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '0.375rem 0.75rem',
    fontSize: '0.875rem',
    fontWeight: isActive ? 600 : 400,
    color: isActive ? '#2563eb' : '#374151',
    textDecoration: 'none',
    borderRadius: '0.375rem',
    backgroundColor: isActive ? '#eff6ff' : 'transparent',
    transition: 'background-color 0.15s, color 0.15s',
  });

  return (
    <nav
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.5rem 1rem',
        borderBottom: '1px solid #e5e7eb',
        backgroundColor: '#fff',
      }}
      aria-label="Main navigation"
    >
      {/* Left side: logo */}
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <NavLink to="/" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none' }}>
          <AppLogo />
        </NavLink>
      </div>

      {/* Right side: language dropdown, then nav links */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        {/* Language dropdown */}
        <div ref={dropdownRef} style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{
              padding: '0.375rem 0.625rem',
              fontSize: '0.8rem',
              fontWeight: 500,
              color: '#374151',
              backgroundColor: '#f9fafb',
              border: '1px solid #d1d5db',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
            aria-label={t.language_label}
            aria-expanded={dropdownOpen}
            aria-haspopup="listbox"
          >
            🌐 {LANGUAGE_SHORT[language]}
            <span style={{ fontSize: '0.6rem', marginLeft: '0.125rem' }}>▼</span>
          </button>

          {dropdownOpen && (
            <div
              role="listbox"
              aria-label={t.language_label}
              style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '0.25rem',
                backgroundColor: '#fff',
                border: '1px solid #e5e7eb',
                borderRadius: '0.375rem',
                boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                zIndex: 50,
                minWidth: '8rem',
                overflow: 'hidden',
              }}
            >
              {LANGUAGE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  role="option"
                  aria-selected={language === opt.value}
                  onClick={() => {
                    setLanguage(opt.value);
                    setDropdownOpen(false);
                  }}
                  style={{
                    display: 'block',
                    width: '100%',
                    padding: '0.5rem 0.75rem',
                    fontSize: '0.825rem',
                    fontWeight: language === opt.value ? 600 : 400,
                    color: language === opt.value ? '#2563eb' : '#374151',
                    backgroundColor: language === opt.value ? '#eff6ff' : '#fff',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Nav links */}
        <NavLink
          to="/"
          end
          style={({ isActive }) => linkStyle(isActive)}
        >
          {t.nav_diagram}
        </NavLink>
        <NavLink
          to="/settings"
          style={({ isActive }) => linkStyle(isActive)}
        >
          {t.nav_settings}
        </NavLink>
      </div>
    </nav>
  );
}
