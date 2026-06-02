// Tests for App's detection persistence (sessionStorage).
//
// The real BrowserRouter lives in main.jsx, outside App, so each test wraps
// <App> in a MemoryRouter and points it at the route under test. Re-mounting
// <App> fresh is exactly what a browser reload does, so these tests verify
// that a result survives a "reload" on /results.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from './App.jsx';

// A complete detection payload, shaped like the real /api/detect response
// (every field Results.jsx reads is present).
const fakeDetection = {
  image_id: 'test-123',
  image_url: '/uploads/test-123.png',
  annotated_url: '/uploads/test-123_annotated.png',
  image_width: 320,
  image_height: 240,
  num_crowns: 1,
  num_filtered: 0,
  conf_threshold: 0.4,
  aspect_ratio_filter: true,
  camera_height_mm: 1000,
  inference_time_ms: 42.5,
  crowns: [
    {
      crown_id: 1,
      bbox: { x1: 10, y1: 20, x2: 110, y2: 120 },
      confidence: 0.91,
      diameter_mm: 85.0,
      diameter_cm: 8.5,
      size_category: 'medium',
    },
  ],
};

function renderAppAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('App detection persistence', () => {
  it('restores a saved detection on /results after a reload', () => {
    // Simulate a prior detection still in sessionStorage, then mount fresh.
    sessionStorage.setItem('lastDetection', JSON.stringify(fakeDetection));

    renderAppAt('/results');

    // The result is shown, NOT the "No results yet" fallback.
    expect(screen.getByText('Detection Results')).toBeInTheDocument();
    expect(screen.queryByText(/No results yet/i)).not.toBeInTheDocument();
  });

  it('does not crash on a corrupt saved value and shows the fallback', () => {
    sessionStorage.setItem('lastDetection', '{bad json');

    // Lazy-init JSON.parse throws -> caught -> null -> fallback (no crash).
    renderAppAt('/results');

    expect(screen.getByText(/No results yet/i)).toBeInTheDocument();
  });

  it('persists the detection to sessionStorage after a successful detect', async () => {
    const user = userEvent.setup();
    // Mock the backend so no real network/inference happens.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => fakeDetection,
        headers: { get: () => null },
      }),
    );

    const { container } = renderAppAt('/upload');

    // Choose a small valid PNG via the (hidden) file input.
    const fileInput = container.querySelector('input[type="file"]');
    const file = new File([new Uint8Array([1, 2, 3])], 'broccoli.png', {
      type: 'image/png',
    });
    await user.upload(fileInput, file);

    // Run detection -> onDetected -> navigate('/results').
    await user.click(screen.getByRole('button', { name: /detect broccoli/i }));

    // We land on Results with the data...
    expect(await screen.findByText('Detection Results')).toBeInTheDocument();
    // ...and the result is now persisted, so a reload would recover it.
    expect(JSON.parse(sessionStorage.getItem('lastDetection'))).toEqual(
      fakeDetection,
    );
  });
});

describe('App dark-mode (no FOUC)', () => {
  it('keeps the pre-set dark class on mount instead of stripping it', () => {
    localStorage.setItem('darkMode', 'true');
    // Simulate the index.html script having set the class before React mounts.
    document.documentElement.classList.add('dark');
    const removeSpy = vi.spyOn(document.documentElement.classList, 'remove');

    renderAppAt('/');

    expect(document.documentElement.classList.contains('dark')).toBe(true);
    // Lazy-init means the apply effect adds (keeps) the class and never
    // strips it on first render - that strip is exactly the visible flash.
    expect(removeSpy).not.toHaveBeenCalledWith('dark');

    removeSpy.mockRestore();
  });

  it('does not enable dark mode when nothing is saved', () => {
    renderAppAt('/');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
