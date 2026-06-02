// Single place for talking to the backend API.
// Keeps endpoint paths, the response.ok check, error parsing, and the
// request-id reference in one spot so pages don't each reinvent them.

const ENDPOINTS = {
  detect: '/api/detect',
  health: '/api/health',
};

// Thrown for any non-ok HTTP response. Carries the status and the server's
// request-id (when present) so the UI can show a support reference.
export class ApiError extends Error {
  constructor(message, { status, ref } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.ref = ref;
  }
}

// Log failures in one place, and only during development, so production stays
// quiet while we still get console output while debugging locally.
function logDev(context, err) {
  if (import.meta.env?.DEV) {
    console.error(`[api] ${context} failed:`, err);
  }
}

// Core request helper: runs fetch, enforces an ok-check before parsing JSON,
// and turns a non-ok response into an ApiError that already includes the ref.
// An AbortError is rethrown untouched so callers can still tell a user cancel
// or a timeout apart from a real failure.
async function request(path, { context, ...options } = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    if (err?.name === 'AbortError') throw err;
    logDev(context, err);
    throw err;
  }

  if (!response.ok) {
    // Read the error body and request id, then build a user-facing message.
    const body = await response.json().catch(() => ({}));
    const ref = response.headers.get('X-Request-ID');
    const detail = body.detail || `Server returned ${response.status}`;
    const message = ref ? `${detail} (ref: ${ref})` : detail;
    const err = new ApiError(message, { status: response.status, ref });
    logDev(context, err);
    throw err;
  }

  return response.json();
}

// Send an image (as multipart form data) to the detection endpoint.
export function detectImage(formData, { signal } = {}) {
  return request(ENDPOINTS.detect, {
    method: 'POST',
    body: formData,
    signal,
    context: 'detect',
  });
}

// Fetch the backend health/readiness summary.
export function getHealth({ signal } = {}) {
  return request(ENDPOINTS.health, { signal, context: 'health' });
}
