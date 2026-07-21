import { NavLink } from 'react-router-dom';
import { AppLogo } from './AppLogo';

/**
 * NavHeader provides the top navigation bar with the application logo
 * and navigation links to the Diagram and Settings pages.
 *
 * Requirements: 13.4, 13.5
 */
export function NavHeader() {
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <NavLink to="/" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none' }}>
          <AppLogo />
        </NavLink>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
        <NavLink
          to="/"
          end
          style={({ isActive }) => linkStyle(isActive)}
        >
          Diagram
        </NavLink>
        <NavLink
          to="/settings"
          style={({ isActive }) => linkStyle(isActive)}
        >
          Settings
        </NavLink>
      </div>
    </nav>
  );
}
