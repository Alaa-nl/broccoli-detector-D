// Tests for the Settings page's health-check abort behaviour (P5-2).

import { render, screen } from '@testing-library/react';
import Settings from './Settings.jsx';

const noop = () => {};
const baseProps = {
  darkMode: false,
  setDarkMode: noop,
  cameraHeight: 1000,
  setCameraHeight: noop,
  confThreshold: 0.4,
  setConfThreshold: noop,
  aspectRatioFilter: true,
  setAspectRatioFilter: noop,
};

describe('Settings health check', () => {
  it('aborts the in-flight health request on unmount', () => {
    let capturedSignal;
    // Never-resolving fetch so the request is still in flight at unmount.
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, opts) => {
        capturedSignal = opts.signal;
        return new Promise(() => {});
      }),
    );

    const { unmount } = render(<Settings {...baseProps} />);

    expect(capturedSignal).toBeInstanceOf(AbortSignal);
    expect(capturedSignal.aborted).toBe(false);

    unmount();

    // Cleanup must abort the request so no state is set on a gone component.
    expect(capturedSignal.aborted).toBe(true);
  });

  it('renders the backend status when the health check succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: async () => ({ status: 'ok', model_loaded: true }),
      }),
    );

    render(<Settings {...baseProps} />);

    expect(
      await screen.findByText(/ok \(model loaded\)/i),
    ).toBeInTheDocument();
  });
});
