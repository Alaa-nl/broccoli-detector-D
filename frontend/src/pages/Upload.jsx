// Upload page.
// Lets the user drop or pick an image, sends it to the backend,
// and navigates to the Results page when the response is ready.

import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileImage, AlertCircle, Loader2 } from 'lucide-react';

// Files larger than this are rejected on the client too,
// so the user gets fast feedback (the backend also checks).
const MAX_FILE_SIZE_MB = 10;
const ALLOWED_TYPES = ['image/jpeg', 'image/png'];

export default function Upload({
  cameraHeight,
  confThreshold,
  aspectRatioFilter,
  onDetected,
}) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  // Validate the chosen file (type + size).
  function pickFile(selected) {
    setError('');
    if (!selected) return;

    if (!ALLOWED_TYPES.includes(selected.type)) {
      setError('Please choose a JPG or PNG image.');
      return;
    }
    if (selected.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      setError(`File is too big. Max size is ${MAX_FILE_SIZE_MB} MB.`);
      return;
    }

    setFile(selected);
    // Show a quick preview so the user knows the right file is chosen.
    setPreviewUrl(URL.createObjectURL(selected));
  }

  // Drag-and-drop handlers.
  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      pickFile(e.dataTransfer.files[0]);
    }
  }

  // Send the file to the backend.
  async function runDetection() {
    if (!file) return;
    setError('');
    setIsLoading(true);

    // Build the multipart form data.
    const formData = new FormData();
    formData.append('file', file);
    formData.append('camera_height_mm', String(cameraHeight));
    formData.append('conf_threshold', String(confThreshold));
    formData.append('aspect_ratio_filter', String(aspectRatioFilter));

    try {
      const response = await fetch('/api/detect', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        // Try to read the error message that FastAPI sends back.
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.detail || `Server returned ${response.status}`);
      }

      const data = await response.json();
      onDetected(data);

      // Move on to the results page.
      navigate('/results');
    } catch (err) {
      console.error(err);
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Upload Image</h1>
        <p className="text-gray-600 dark:text-gray-300 mt-1">
          Select a broccoli field image to start detection.
        </p>
      </header>

      {/* Drop zone. */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`card p-8 text-center cursor-pointer border-2 border-dashed transition-colors ${
          isDragging
            ? 'border-broccoli-500 bg-broccoli-50 dark:bg-gray-700'
            : 'border-gray-300 dark:border-gray-600 hover:border-broccoli-400'
        }`}
      >
        {previewUrl ? (
          // Show the chosen image preview.
          <div className="space-y-3">
            <img
              src={previewUrl}
              alt="Preview"
              className="max-h-64 mx-auto rounded-lg shadow-sm"
            />
            <div className="flex items-center justify-center gap-2 text-sm text-gray-600 dark:text-gray-400">
              <FileImage className="w-4 h-4" />
              {file?.name}
            </div>
          </div>
        ) : (
          // Show the empty drop zone.
          <div className="space-y-3">
            <UploadCloud className="w-12 h-12 mx-auto text-gray-400" />
            <div className="font-semibold text-lg">Drag & Drop Image Here</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              or click to browse files
            </div>
            <div className="flex gap-2 justify-center text-xs">
              <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">.JPG</span>
              <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">.PNG</span>
              <span className="px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full">Max 10 MB</span>
            </div>
          </div>
        )}

        {/* Hidden file input, triggered by the click above. */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={(e) => pickFile(e.target.files?.[0])}
          className="hidden"
        />
      </div>

      {/* Tips card. */}
      <div className="card p-4 bg-yellow-50 dark:bg-gray-800 border-yellow-200 dark:border-yellow-900">
        <h3 className="font-semibold mb-2 text-yellow-900 dark:text-yellow-300">
          Tips for best results
        </h3>
        <ul className="text-sm text-yellow-900/80 dark:text-yellow-200/80 space-y-1 list-disc list-inside">
          <li>Take the photo from above (top-down view).</li>
          <li>Make sure the broccoli crown is visible.</li>
          <li>Avoid very dark or very bright images.</li>
        </ul>
      </div>

      {/* Error message. */}
      {error && (
        <div className="card p-4 bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-red-700 dark:text-red-300">{error}</div>
        </div>
      )}

      {/* Detect button. */}
      <button
        onClick={runDetection}
        disabled={!file || isLoading}
        className="btn-primary w-full flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Detecting...
          </>
        ) : (
          'Detect Broccoli'
        )}
      </button>

      <div className="text-xs text-gray-500 dark:text-gray-400 text-center space-y-1">
        <div>
          Camera height: <strong>{cameraHeight} mm</strong>
          {' · '}
          Min confidence: <strong>{(confThreshold * 100).toFixed(0)}%</strong>
          {' · '}
          Leaf filter: <strong>{aspectRatioFilter ? 'on' : 'off'}</strong>
        </div>
        <div>Change these in Settings.</div>
      </div>
    </div>
  );
}
