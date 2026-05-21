// Settings page.
// Lets the user change dark mode, the camera height (for size
// estimation), and shows information about the loaded model.

import { useEffect, useState } from 'react';
import { Moon, Sun, RotateCcw, Ruler } from 'lucide-react';

export default function Settings({
  darkMode,
  setDarkMode,
  cameraHeight,
  setCameraHeight,
}) {
  // Local state for the camera height input.
  // We commit it to the parent only when the user finishes typing.
  const [heightInput, setHeightInput] = useState(String(cameraHeight));

  // Health info from the backend.
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setHealth(data))
      .catch(() => setHealth({ status: 'unreachable', model_loaded: false }));
  }, []);

  function commitHeight() {
    const value = parseFloat(heightInput);
    if (Number.isFinite(value) && value > 100 && value < 5000) {
      setCameraHeight(value);
    } else {
      // Reset to the saved value if the input was bad.
      setHeightInput(String(cameraHeight));
    }
  }

  function resetDefaults() {
    setDarkMode(false);
    setCameraHeight(1000);
    setHeightInput('1000');
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-gray-600 dark:text-gray-300 mt-1">
          Customise the look and feel of the app.
        </p>
      </header>

      {/* Appearance card. */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold uppercase text-gray-500 dark:text-gray-400 mb-3 tracking-wider">
          Appearance
        </h2>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {darkMode ? (
              <Moon className="w-5 h-5 text-broccoli-600" />
            ) : (
              <Sun className="w-5 h-5 text-yellow-500" />
            )}
            <div>
              <div className="font-semibold">Dark Mode</div>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                Switch between light and dark theme.
              </div>
            </div>
          </div>
          {/* Simple toggle switch. */}
          <button
            onClick={() => setDarkMode(!darkMode)}
            aria-label="Toggle dark mode"
            className={`relative w-12 h-7 rounded-full transition-colors ${
              darkMode ? 'bg-broccoli-600' : 'bg-gray-300'
            }`}
          >
            <span
              className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm ${
                darkMode ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </section>

      {/* Camera height card (drives the size estimator). */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold uppercase text-gray-500 dark:text-gray-400 mb-3 tracking-wider">
          Size Estimation
        </h2>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Ruler className="w-5 h-5 text-broccoli-600" />
            <div className="flex-1">
              <label htmlFor="cam-h" className="font-semibold block">
                Camera height (mm)
              </label>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                How high above the ground the camera was held.
              </div>
            </div>
          </div>
          <input
            id="cam-h"
            type="number"
            min={100}
            max={5000}
            step={50}
            value={heightInput}
            onChange={(e) => setHeightInput(e.target.value)}
            onBlur={commitHeight}
            onKeyDown={(e) => e.key === 'Enter' && commitHeight()}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 focus:ring-2 focus:ring-broccoli-500 focus:border-broccoli-500"
          />
          <div className="text-xs text-gray-500 dark:text-gray-400">
            Typical range: 800-1500 mm. Default: 1000 mm.
          </div>
        </div>
      </section>

      {/* Reset button. */}
      <button
        onClick={resetDefaults}
        className="btn-secondary w-full flex items-center justify-center gap-2"
      >
        <RotateCcw className="w-5 h-5" />
        Reset to Defaults
      </button>

      {/* Model info card (matches the wireframe in the TFGD). */}
      <section className="card p-5 bg-gray-900 dark:bg-gray-800 text-white">
        <h2 className="font-semibold mb-3">Model Information</h2>
        <dl className="text-sm space-y-1">
          <Row label="Architecture" value="YOLOv8n (Ultralytics)" />
          <Row label="Parameters" value="3.0M" />
          <Row label="Training mAP@0.5" value="0.976" />
          <Row label="Mean IoU" value="0.916" />
          <Row label="Weights" value="best.pt (about 6 MB)" />
          <Row
            label="Server status"
            value={
              health
                ? `${health.status} (model ${
                    health.model_loaded ? 'loaded' : 'NOT loaded'
                  })`
                : 'checking...'
            }
          />
        </dl>
      </section>
    </div>
  );
}

// Small key/value row used in the model info card.
function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-gray-400">{label}</dt>
      <dd className="font-mono text-right">{value}</dd>
    </div>
  );
}
