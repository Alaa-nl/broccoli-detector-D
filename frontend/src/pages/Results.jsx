// Results page.
// Shows the annotated image, a summary, and a list of every crown.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Zap, Camera, Ruler, ImageOff } from 'lucide-react';

// Colour for each size category badge.
const categoryColours = {
  small:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  medium: 'bg-broccoli-100 text-broccoli-800 dark:bg-broccoli-900/40 dark:text-broccoli-300',
  large:  'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
};

export default function Results({ detection }) {
  // Which crown the user has clicked on (for highlight).
  const [selectedId, setSelectedId] = useState(null);
  // The annotated image is a server file with a TTL, so a reload after it
  // expires (or a server restart) makes the URL 404. Track that so we can show
  // a clear message instead of a silent broken-image icon - the detection
  // details below come from the saved payload and are still valid.
  const [imageError, setImageError] = useState(false);

  // Toggle a crown's expanded details (shared by click and keyboard).
  const toggleCrown = (id) =>
    setSelectedId((prev) => (prev === id ? null : id));

  // If the user lands here directly without running detection,
  // send them to the Upload page with a friendly message.
  if (!detection) {
    return (
      <div className="card p-8 text-center space-y-4">
        <h2 className="text-xl font-bold">No results yet</h2>
        <p className="text-gray-600 dark:text-gray-300">
          Please upload an image first to see detection results.
        </p>
        <Link to="/upload" className="btn-primary inline-block">
          Go to Upload
        </Link>
      </div>
    );
  }

  // Treat a missing/malformed crowns field as an empty list so a corrupt
  // payload renders an empty result instead of throwing.
  const crowns = Array.isArray(detection.crowns) ? detection.crowns : [];
  const numCrowns = detection.num_crowns ?? crowns.length;

  // Build a small summary at the top.
  const avgDiameter = crowns.length > 0
    ? crowns.reduce((sum, c) => sum + (c.diameter_cm ?? 0), 0) / crowns.length
    : 0;

  // When nothing is found AND strictness was raised above the default (0.40),
  // the high confidence threshold is the most likely reason - so point the user
  // to Settings. (A tester hit exactly this: at 90% strictness some photos
  // returned no crowns even though the page loaded fine.)
  const confThreshold = detection.conf_threshold;
  const strictnessMayHideCrowns =
    crowns.length === 0 &&
    Number.isFinite(confThreshold) &&
    confThreshold > 0.4;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <Link
          to="/upload"
          className="text-sm text-broccoli-700 dark:text-broccoli-400 flex items-center gap-1 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" /> Back to upload
        </Link>
      </header>

      <h1 className="text-2xl font-bold">Detection Results</h1>

      {/* Annotated image. A server file with a TTL, so it can 404 after the
          retention sweep or a restart - show a message instead of a broken
          icon when that happens. */}
      <div className="card p-2 overflow-hidden">
        {imageError ? (
          <div className="w-full rounded-lg bg-gray-100 dark:bg-gray-800 px-4 py-12 text-center">
            <ImageOff
              className="w-8 h-8 mx-auto mb-2 text-gray-400 dark:text-gray-500"
              aria-hidden="true"
            />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
              Annotated image unavailable
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              The file may have expired or the server was restarted. The
              detection details below are still valid.
            </p>
          </div>
        ) : (
          <img
            src={detection.annotated_url}
            alt="Detection result with green bounding boxes"
            className="w-full rounded-lg"
            onError={() => setImageError(true)}
          />
        )}
      </div>

      {/* Summary cards. */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard
          icon={<Camera className="w-5 h-5" />}
          label="Crowns found"
          value={numCrowns}
        />
        <SummaryCard
          icon={<Ruler className="w-5 h-5" />}
          label="Average size"
          value={avgDiameter > 0 ? `${avgDiameter.toFixed(1)} cm` : '-'}
        />
        <SummaryCard
          icon={<Zap className="w-5 h-5" />}
          label="Speed"
          value={
            Number.isFinite(detection.inference_time_ms)
              ? `${detection.inference_time_ms.toFixed(0)} ms`
              : '-'
          }
        />
        <SummaryCard
          icon={<Camera className="w-5 h-5" />}
          label="Image size"
          value={`${detection.image_width ?? '?'}\u00d7${detection.image_height ?? '?'}`}
        />
      </div>

      {/* List of detected crowns. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-3">
          Detected Crowns ({numCrowns})
        </h2>

        {crowns.length === 0 ? (
          <div className="text-sm text-gray-500 dark:text-gray-400 space-y-2">
            <p>
              The model did not find any crowns in this image. Try another
              photo, or check that the crown is clearly visible.
            </p>
            {strictnessMayHideCrowns && (
              <p>
                Your strictness is set to {(confThreshold * 100).toFixed(0)}% —
                try lowering it in{' '}
                <Link
                  to="/settings"
                  className="text-broccoli-700 dark:text-broccoli-400 hover:underline"
                >
                  Settings
                </Link>{' '}
                to surface less-confident crowns.
              </p>
            )}
          </div>
        ) : (
          <ul className="space-y-2">
            {crowns.map((crown) => (
              <li
                key={crown.crown_id}
                role="button"
                tabIndex={0}
                aria-expanded={selectedId === crown.crown_id}
                onClick={() => toggleCrown(crown.crown_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleCrown(crown.crown_id);
                  }
                }}
                className={`p-3 rounded-lg border cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-broccoli-500 ${
                  selectedId === crown.crown_id
                    ? 'bg-broccoli-50 dark:bg-gray-700 border-broccoli-400'
                    : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="bg-broccoli-600 text-white w-8 h-8 rounded-full flex items-center justify-center font-bold flex-shrink-0">
                      {crown.crown_id}
                    </span>
                    <div className="min-w-0">
                      <div className="font-semibold">
                        {crown.diameter_cm?.toFixed(1) ?? '-'} cm
                        <span className="text-gray-500 dark:text-gray-400 font-normal ml-2 text-sm">
                          ({crown.diameter_mm?.toFixed(0) ?? '-'} mm)
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Confidence:{' '}
                        {Number.isFinite(crown.confidence)
                          ? `${(crown.confidence * 100).toFixed(1)}%`
                          : '-'}
                      </div>
                    </div>
                  </div>
                  <span
                    className={`text-xs font-semibold px-3 py-1 rounded-full ${
                      categoryColours[crown.size_category] || ''
                    }`}
                  >
                    {crown.size_category}
                  </span>
                </div>

                {/* Extra details only when selected. */}
                {selectedId === crown.crown_id && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-400 space-y-1">
                    <div>
                      Bounding box: ({crown.bbox?.x1?.toFixed(0) ?? '-'},{' '}
                      {crown.bbox?.y1?.toFixed(0) ?? '-'}) to (
                      {crown.bbox?.x2?.toFixed(0) ?? '-'},{' '}
                      {crown.bbox?.y2?.toFixed(0) ?? '-'})
                    </div>
                    <div>
                      Size in pixels:{' '}
                      {Number.isFinite(crown.bbox?.x2) && Number.isFinite(crown.bbox?.x1)
                        ? (crown.bbox.x2 - crown.bbox.x1).toFixed(0)
                        : '-'}{' '}
                      x{' '}
                      {Number.isFinite(crown.bbox?.y2) && Number.isFinite(crown.bbox?.y1)
                        ? (crown.bbox.y2 - crown.bbox.y1).toFixed(0)
                        : '-'}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Disclaimer note about the size estimate. */}
      <div className="card p-4 text-xs text-gray-600 dark:text-gray-400 space-y-2">
        <div>
          <strong>Size estimate:</strong> bounding box converted to mm
          using a pinhole camera model with the camera at{' '}
          {detection.camera_height_mm ?? '?'} mm above the ground (Intel
          RealSense D415, 69.4° horizontal field of view). Change camera
          height in Settings to calibrate.
        </div>
        <div>
          <strong>Filters:</strong> minimum confidence{' '}
          {Number.isFinite(detection.conf_threshold)
            ? `${(detection.conf_threshold * 100).toFixed(0)}%`
            : '-'}{' '}
          · leaf filter {detection.aspect_ratio_filter ? 'on' : 'off'}
          {detection.num_filtered > 0 && (
            <span>
              {' '}· removed {detection.num_filtered} elongated box
              {detection.num_filtered === 1 ? '' : 'es'}
            </span>
          )}
        </div>
      </div>

      <Link to="/upload" className="btn-secondary inline-block">
        Try another image
      </Link>
    </div>
  );
}

// Small helper for the four summary cards at the top.
function SummaryCard({ icon, label, value }) {
  return (
    <div className="card p-3">
      <div className="text-broccoli-600 dark:text-broccoli-400 mb-1">
        {icon}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
      <div className="font-semibold text-lg">{value}</div>
    </div>
  );
}
