// Vitest configuration for the frontend component tests.
// Tests run on Node (in a Docker container) inside a jsdom-simulated DOM,
// so we can render React components and assert real behaviour without a
// browser. Kept separate from vite.config.js (which is dev-server only).
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom gives components a document/window (and sessionStorage).
    environment: 'jsdom',
    // Expose describe/it/expect/vi without importing them in every file.
    globals: true,
    // Auto-restore any vi.stubGlobal (e.g. fetch) after each test.
    unstubGlobals: true,
    // Runs once before the suite: matchers, browser-API stubs, cleanup.
    setupFiles: './src/test/setup.js',
  },
});
