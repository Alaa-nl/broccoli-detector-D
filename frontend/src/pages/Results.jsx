// Results page.
// Shows the annotated image, a summary, and a list of every crown.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Zap, Camera, Ruler } from 'lucide-react';

// Colour for each size category badge.
const categoryColours = {
  small:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
  medium: 'bg-broccoli-100 text-broccoli-800 dark:bg-broccoli-900/40 dark:text-broccoli-300',
  large:  'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
};

export default function Results({ detection }) {
  // Which crown the user has clicked on (for highlight).
  const [selectedId, setSelectedId] = useState(null);

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

  // Build a small summary at the top.
  const avgDiameter = detection.crowns.length > 0
    ? detection.crowns.reduce((sum, c) => sum + c.diameter_cm, 0) /
      detection.crowns.length
    : 0;

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

      {/* Annotated image. */}
      <div className="card p-2 overflow-hidden">
        <img
          src={detection.annotated_url}
          alt="Detection result with green bounding boxes"
          className="w-full rounded-lg"
        />
      </div>

      {/* Summary cards. */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard
          icon={<Camera className="w-5 h-5" />}
          label="Crowns found"
          value={detection.num_crowns}
        />
        <SummaryCard
          icon={<Ruler className="w-5 h-5" />}
          label="Average size"
          value={avgDiameter > 0 ? `${avgDiameter.toFixed(1)} cm` : '-'}
        />
        <SummaryCard
          icon={<Zap className="w-5 h-5" />}
          label="Speed"
          value={`${detection.inference_time_ms.toFixed(0)} ms`}
        />
        <SummaryCard
          icon={<Camera className="w-5 h-5" />}
          label="Image size"
          value={`${detection.image_width}\u00d7${detection.image_height}`}
        />
      </div>

      {/* List of detected crowns. */}
      <section className="card p-5">
        <h2 className="font-semibold mb-3">
          Detected Crowns ({detection.num_crowns})
        </h2>

        {detection.crowns.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            The model did not find any crowns in this image. Try another
            photo, or check that the crown is clearly visible.
          </p>
        ) : (
          <ul className="space-y-2">
            {detection.crowns.map((crown) => (
              <li
                key={crown.crown_id}
                onClick={() => setSelectedId(
                  selectedId === crown.crown_id ? null : crown.crown_id
                )}
                className={`p-3 rounded-lg border cursor-pointer transition-colors ${
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
                        {crown.diameter_cm.toFixed(1)} cm
                        <span className="text-gray-500 dark:text-gray-400 font-normal ml-2 text-sm">
                          ({crown.diameter_mm.toFixed(0)} mm)
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        Confidence: {(crown.confidence * 100).toFixed(1)}%
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
                      Bounding box: ({crown.bbox.x1.toFixed(0)},{' '}
                      {crown.bbox.y1.toFixed(0)}) to (
                      {crown.bbox.x2.toFixed(0)},{' '}
                      {crown.bbox.y2.toFixed(0)})
                    </div>
                    <div>
                      Size in pixels:{' '}
                      {(crown.bbox.x2 - crown.bbox.x1).toFixed(0)} x{' '}
                      {(crown.bbox.y2 - crown.bbox.y1).toFixed(0)}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Disclaimer note about the size estimate. */}
      <div className="card p-4 text-xs text-gray-600 dark:text-gray-400">
        <strong>Note about size:</strong> Crown size is estimated from the
        bounding box using a pinhole camera model with the camera at{' '}
        {detection.camera_height_mm} mm above the ground (Intel RealSense
        D415, 69.4° horizontal field of view). You can change the camera
        height in Settings to calibrate the result.
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
