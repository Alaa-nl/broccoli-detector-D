// Settings page.
// Lets the user change dark mode, the camera height (for size
// estimation), and shows information about the loaded model.

import { useEffect, useState } from 'react';
import { Moon, Sun, RotateCcw, Ruler, Target, Leaf } from 'lucide-react';
import { getHealth } from '../api/client';
import { MODEL_INFO } from '../constants/model.js';

// Give up on the health check after this long so it can't sit on
// "checking..." forever if the backend never answers.
const HEALTH_TIMEOUT_MS = 10000;

export default function Settings({
  darkMode,
  setDarkMode,
  cameraHeight,
  setCameraHeight,
  confThreshold,
  setConfThreshold,
  aspectRatioFilter,
  setAspectRatioFilter,
}) {
  // Local state for the camera height input.
  // We commit it to the parent only when the user finishes typing.
  const [heightInput, setHeightInput] = useState(String(cameraHeight));

  // Health info from the backend.
  const [health, setHealth] = useState(null);

  useEffect(() => {
    // Abort on a timeout (report unreachable) or on unmount (stay silent so
    // we don't set state on a gone component). `timedOut` separates the two,
    // since both surface as an AbortError.
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, HEALTH_TIMEOUT_MS);

    getHealth({ signal: controller.signal })
      .then((data) => setHealth(data))
      .catch((err) => {
        // Ignore an unmount-abort; a real timeout or network error still
        // reports the backend as unreachable.
        if (err.name !== 'AbortError' || timedOut) {
          setHealth({ status: 'unreachable', model_loaded: false });
        }
      })
      .finally(() => clearTimeout(timer));

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
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
    setConfThreshold(0.40);
    setAspectRatioFilter(true);
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

      {/* Detection sensitivity (confidence threshold). */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold uppercase text-gray-500 dark:text-gray-400 mb-3 tracking-wider">
          Detection Strictness
        </h2>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Target className="w-5 h-5 text-broccoli-600" />
            <div className="flex-1">
              <div className="font-semibold">
                Minimum confidence: {(confThreshold * 100).toFixed(0)}%
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                Higher = fewer false positives, but may miss some crowns.
              </div>
            </div>
          </div>
          <input
            type="range"
            min={0.10}
            max={0.90}
            step={0.05}
            value={confThreshold}
            onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
            className="w-full accent-broccoli-600"
          />
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>10% (more boxes)</span>
            <span>Default: 40%</span>
            <span>90% (stricter)</span>
          </div>
        </div>
      </section>

      {/* Aspect ratio (leaf) filter. */}
      <section className="card p-5">
        <h2 className="text-sm font-semibold uppercase text-gray-500 dark:text-gray-400 mb-3 tracking-wider">
          Leaf Filter
        </h2>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Leaf className="w-5 h-5 text-broccoli-600" />
            <div>
              <div className="font-semibold">Drop elongated boxes</div>
              <div className="text-sm text-gray-500 dark:text-gray-400">
                Real crowns are roughly square from above. Long boxes
                are usually leaves.
              </div>
            </div>
          </div>
          <button
            onClick={() => setAspectRatioFilter(!aspectRatioFilter)}
            aria-label="Toggle leaf filter"
            className={`relative w-12 h-7 rounded-full transition-colors flex-shrink-0 ml-3 ${
              aspectRatioFilter ? 'bg-broccoli-600' : 'bg-gray-300'
            }`}
          >
            <span
              className={`absolute top-1 left-1 w-5 h-5 bg-white rounded-full transition-transform shadow-sm ${
                aspectRatioFilter ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
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

      {/* Model info card: a normal card (light in light mode, dark in dark
          mode), consistent with the other sections above. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-3">Model Information</h2>
        <dl className="text-sm space-y-1">
          <Row label="Architecture" value={MODEL_INFO.architecture} />
          <Row label="Parameters" value={MODEL_INFO.parameters} />
          <Row label="Training mAP@0.5" value={MODEL_INFO.trainingMap} />
          <Row label="Mean IoU" value={MODEL_INFO.meanIoU} />
          <Row label="Weights" value={MODEL_INFO.weights} />
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
      <dt className="text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="font-mono text-right">{value}</dd>
    </div>
  );
}
