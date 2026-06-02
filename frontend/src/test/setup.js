// Test setup, loaded once before the suite (see vitest.config.js).

// Adds DOM matchers like toBeInTheDocument() / toHaveTextContent().
import '@testing-library/jest-dom/vitest';

import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom doesn't implement the object-URL API the Upload page uses for
// image previews, so stub it (a no-op blob URL is enough for tests).
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = vi.fn(() => 'blob:test');
}
if (typeof URL.revokeObjectURL !== 'function') {
  URL.revokeObjectURL = vi.fn();
}

// Unmount React trees and wipe storage between tests so they stay isolated.
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  // The dark-mode tests toggle this class on <html>; reset it so it can't
  // leak into another test.
  document.documentElement.classList.remove('dark');
});
