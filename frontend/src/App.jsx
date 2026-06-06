// Main App component.
//
// This file sets up the page routing and shares the detection
// result between the Upload page (which creates it) and the
// Results page (which shows it).

import { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';

import BottomNav from './components/BottomNav.jsx';
import Header from './components/Header.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import Home from './pages/Home.jsx';
import Upload from './pages/Upload.jsx';
import Results from './pages/Results.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';
import { clampNumber } from './utils/number.js';

// Best-effort localStorage write: some privacy modes / locked-down browsers
// throw on access, so persistence must never crash a render.
function persistSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked or full — non-fatal, settings just won't persist */
  }
}

export default function App() {
  // Used as the error-boundary key below, so navigating to another tab
  // remounts the boundary and clears a crash without a full reload.
  const location = useLocation();

  // The latest detection result. The Upload page sets it, the Results page
  // reads it. It is persisted to sessionStorage so a refresh, a new tab, or a
  // shared /results URL doesn't discard the result the user just waited for.
  // Lazy-init restores any saved result on first render; the effect below
  // keeps the saved copy in sync. (getItem returns null when unset, and
  // JSON.parse(null) is null, so the no-saved-result case is safe.)
  const [detection, setDetection] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('lastDetection'));
    } catch {
      return null; // corrupt stored value — ignore and start fresh
    }
  });

  // User settings (saved in localStorage so they survive a reload).
  // darkMode is lazy-initialised from storage so React's first render matches
  // the class the inline script in index.html already set before paint - the
  // apply effect below then keeps the class instead of stripping it (no flash).
  const [darkMode, setDarkMode] = useState(() => {
    try {
      return localStorage.getItem('darkMode') === 'true';
    } catch {
      return false;
    }
  });
  const [cameraHeight, setCameraHeight] = useState(1000);
  // Detection sensitivity (higher = stricter, fewer false positives).
  const [confThreshold, setConfThreshold] = useState(0.40);
  // Drop boxes that are too elongated (probably leaves, not crowns).
  const [aspectRatioFilter, setAspectRatioFilter] = useState(true);

  // Load saved settings on first render. (darkMode is handled by the lazy
  // initialiser above so it can take effect before paint.)
  useEffect(() => {
    // Reading localStorage can throw where storage is blocked/disabled (some
    // privacy modes, locked-down browsers); fall back to the state defaults
    // instead of crashing on mount. Clamp restored values too so a corrupt or
    // out-of-range stored setting ("NaN", a height of 999999) can't leak in.
    try {
      const savedHeight = clampNumber(localStorage.getItem('cameraHeight'), 100, 5000, 1000);
      const savedConf = clampNumber(localStorage.getItem('confThreshold'), 0.10, 0.90, 0.40);
      const savedArf = localStorage.getItem('aspectRatioFilter');
      setCameraHeight(savedHeight);
      setConfThreshold(savedConf);
      // Default to true if not set yet.
      setAspectRatioFilter(savedArf === null ? true : savedArf === 'true');
    } catch {
      /* storage unavailable — keep the in-memory defaults */
    }
  }, []);

  // Apply / remove the dark class on the <html> element
  // whenever darkMode changes. Tailwind reads this class.
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    persistSetting('darkMode', String(darkMode));
  }, [darkMode]);

  useEffect(() => {
    persistSetting('cameraHeight', String(cameraHeight));
  }, [cameraHeight]);

  useEffect(() => {
    persistSetting('confThreshold', String(confThreshold));
  }, [confThreshold]);

  useEffect(() => {
    persistSetting('aspectRatioFilter', String(aspectRatioFilter));
  }, [aspectRatioFilter]);

  // Persist the latest detection so the Results page survives a reload.
  // A new detection overwrites the saved one; we never store an empty value.
  useEffect(() => {
    if (!detection) return;
    try {
      sessionStorage.setItem('lastDetection', JSON.stringify(detection));
    } catch {
      /* storage full or unavailable (e.g. private mode) — non-fatal */
    }
  }, [detection]);

  return (
    <div className="min-h-screen pb-24 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <Header />

      <main className="max-w-3xl mx-auto px-4 py-6">
        <ErrorBoundary key={location.pathname}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/upload"
            element={
              <Upload
                cameraHeight={cameraHeight}
                confThreshold={confThreshold}
                aspectRatioFilter={aspectRatioFilter}
                onDetected={setDetection}
              />
            }
          />
          <Route
            path="/results"
            element={<Results detection={detection} />}
          />
          <Route
            path="/settings"
            element={
              <Settings
                darkMode={darkMode}
                setDarkMode={setDarkMode}
                cameraHeight={cameraHeight}
                setCameraHeight={setCameraHeight}
                confThreshold={confThreshold}
                setConfThreshold={setConfThreshold}
                aspectRatioFilter={aspectRatioFilter}
                setAspectRatioFilter={setAspectRatioFilter}
              />
            }
          />
          <Route path="/about" element={<About />} />

          {/* Fallback: any unknown URL goes home. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ErrorBoundary>
      </main>

      <BottomNav />
    </div>
  );
}
