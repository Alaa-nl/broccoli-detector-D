// Main App component.
//
// This file sets up the page routing and shares the detection
// result between the Upload page (which creates it) and the
// Results page (which shows it).

import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import BottomNav from './components/BottomNav.jsx';
import Header from './components/Header.jsx';
import Home from './pages/Home.jsx';
import Upload from './pages/Upload.jsx';
import Results from './pages/Results.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';

export default function App() {
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
  const [darkMode, setDarkMode] = useState(false);
  const [cameraHeight, setCameraHeight] = useState(1000);
  // Detection sensitivity (higher = stricter, fewer false positives).
  const [confThreshold, setConfThreshold] = useState(0.40);
  // Drop boxes that are too elongated (probably leaves, not crowns).
  const [aspectRatioFilter, setAspectRatioFilter] = useState(true);

  // Load saved settings on first render.
  useEffect(() => {
    const savedDark = localStorage.getItem('darkMode') === 'true';
    const savedHeight = parseFloat(localStorage.getItem('cameraHeight') || '1000');
    const savedConf = parseFloat(localStorage.getItem('confThreshold') || '0.40');
    const savedArf = localStorage.getItem('aspectRatioFilter');
    setDarkMode(savedDark);
    setCameraHeight(savedHeight);
    setConfThreshold(savedConf);
    // Default to true if not set yet.
    setAspectRatioFilter(savedArf === null ? true : savedArf === 'true');
  }, []);

  // Apply / remove the dark class on the <html> element
  // whenever darkMode changes. Tailwind reads this class.
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('darkMode', String(darkMode));
  }, [darkMode]);

  useEffect(() => {
    localStorage.setItem('cameraHeight', String(cameraHeight));
  }, [cameraHeight]);

  useEffect(() => {
    localStorage.setItem('confThreshold', String(confThreshold));
  }, [confThreshold]);

  useEffect(() => {
    localStorage.setItem('aspectRatioFilter', String(aspectRatioFilter));
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
      </main>

      <BottomNav />
    </div>
  );
}
