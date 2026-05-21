// Fixed bottom navigation bar (4 tabs: Home, Upload, Settings, About).
// Matches the design from the Deliverable C wireframes.

import { Home, Upload, Settings, Info } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const tabs = [
  { to: '/',         label: 'Home',     icon: Home },
  { to: '/upload',   label: 'Upload',   icon: Upload },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/about',    label: 'About',    icon: Info },
];

export default function BottomNav() {
  return (
    <nav className="bottom-nav">
      {tabs.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          // NavLink gives us isActive automatically.
          className={({ isActive }) =>
            `flex flex-col items-center text-xs font-medium transition-colors ${
              isActive
                ? 'text-broccoli-600 dark:text-broccoli-400'
                : 'text-gray-500 dark:text-gray-400 hover:text-broccoli-600'
            }`
          }
        >
          <Icon className="w-6 h-6 mb-1" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
