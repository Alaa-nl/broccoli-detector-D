// Small numeric helpers shared across the app.

// Parse a value to a finite number and clamp it into [min, max].
// Returns `fallback` when the value is missing, non-numeric, or NaN -
// used to sanitise settings restored from localStorage so a corrupt or
// out-of-range stored value can never reach the UI or a request.
export function clampNumber(value, min, max, fallback) {
  const n = typeof value === 'number' ? value : parseFloat(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}
