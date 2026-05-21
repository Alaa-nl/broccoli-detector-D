// Vite build configuration.
// Vite is the build tool that bundles our React code
// and runs the development server.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Forward all /api/* and /uploads/* requests to the backend.
    // This way the React app can call /api/detect during development
    // without worrying about CORS or full URLs.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
