// Client-side upload limits, kept in one place so the validation logic, the
// input's `accept` attribute, and the on-screen hints can't drift apart.
// The backend enforces its own limits regardless; these are for fast feedback.
export const ALLOWED_TYPES = ['image/jpeg', 'image/png'];
export const MAX_FILE_SIZE_MB = 10;

// Derived from ALLOWED_TYPES for the <input accept> attribute.
export const ACCEPT = ALLOWED_TYPES.join(',');

// Short labels for the format hint chips.
export const TYPE_LABELS = { 'image/jpeg': '.JPG', 'image/png': '.PNG' };
