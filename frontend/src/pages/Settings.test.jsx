// Tests for the Settings page's health/metadata fetching and abort
// behaviour, plus the live-vs-fallback model info rows.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Settings from './Settings.jsx';
import { MODEL_INFO } from '../constants/model.js';

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

// Mounting Settings now fires TWO requests (health + metadata), so a single
// mockResolvedValue would feed the same body to both. Route the stub by URL
// instead, defaulting each endpoint to a never-resolving promise so a test
// only has to script the endpoint it actually cares about.
const never = () => new Promise(() => {});
function stubFetchRoutes({ health = never, metadata = never } = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url, opts) =>
      url === '/api/metadata' ? metadata(url, opts) : health(url, opts),
    ),
  );
}

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
        ok: true,
        json: async () => ({ status: 'ok', model_loaded: true }),
      }),
    );

    render(<Settings {...baseProps} />);

    expect(
      await screen.findByText(/ok \(model loaded\)/i),
    ).toBeInTheDocument();
  });

  it('renders the model-info rows from MODEL_INFO', () => {
    // Never-resolving health fetch; we only care about the static model rows.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    render(<Settings {...baseProps} />);

    expect(screen.getByText(MODEL_INFO.parameters)).toBeInTheDocument();
    expect(screen.getByText(MODEL_INFO.architecture)).toBeInTheDocument();
    expect(screen.getByText(MODEL_INFO.weights)).toBeInTheDocument();
  });

  it('shows "degraded" (not "unreachable") when /health returns a 503 body', async () => {
    // Backend up but model not loaded: /health returns HTTP 503 with a body.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        headers: { get: () => null },
        json: async () => ({ status: 'degraded', model_loaded: false }),
      }),
    );

    render(<Settings {...baseProps} />);

    expect(
      await screen.findByText(/degraded \(model NOT loaded\)/i),
    ).toBeInTheDocument();
  });
});

describe('Settings camera-height input', () => {
  it('accepts the boundary value 5000 instead of reverting it', async () => {
    // Health never resolves; we only exercise the height input here.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const setCameraHeight = vi.fn();
    const user = userEvent.setup();

    render(<Settings {...baseProps} setCameraHeight={setCameraHeight} />);

    const input = screen.getByLabelText(/camera height/i);
    await user.clear(input);
    await user.type(input, '5000');
    await user.tab(); // blur -> commitHeight

    expect(setCameraHeight).toHaveBeenCalledWith(5000);
  });

  it('accepts the lower boundary value 100 instead of reverting it', async () => {
    // Regression test for finding #2 (the >100 vs >=100 bound): exactly 100 mm
    // is in range and must be committed, not snapped back.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const setCameraHeight = vi.fn();
    const user = userEvent.setup();

    render(<Settings {...baseProps} setCameraHeight={setCameraHeight} />);

    const input = screen.getByLabelText(/camera height/i);
    await user.clear(input);
    await user.type(input, '100');
    await user.tab(); // blur -> commitHeight

    expect(setCameraHeight).toHaveBeenCalledWith(100);
  });

  it('reverts an out-of-range value to the saved height on blur', async () => {
    // The reject branch: a value outside [100, 5000] is not committed; the
    // field snaps back to the last good value instead.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const setCameraHeight = vi.fn();
    const user = userEvent.setup();

    render(
      <Settings
        {...baseProps}
        cameraHeight={1000}
        setCameraHeight={setCameraHeight}
      />,
    );

    const input = screen.getByLabelText(/camera height/i);
    await user.clear(input);
    await user.type(input, '99'); // just below the 100 mm floor
    await user.tab(); // blur -> commitHeight

    expect(setCameraHeight).not.toHaveBeenCalled();
    expect(input).toHaveValue(1000); // snapped back to the saved value
  });

  it('commits a typed-but-un-blurred height when the page unmounts', async () => {
    // Mimics navigating away (e.g. browser back) without blurring the field:
    // the value must still reach the parent so Upload uses the latest height.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const setCameraHeight = vi.fn();
    const user = userEvent.setup();

    const { unmount } = render(
      <Settings {...baseProps} setCameraHeight={setCameraHeight} />,
    );

    const input = screen.getByLabelText(/camera height/i);
    await user.clear(input);
    await user.type(input, '1500'); // no blur / Enter
    expect(setCameraHeight).not.toHaveBeenCalled();

    unmount();

    expect(setCameraHeight).toHaveBeenCalledWith(1500);
  });

  it('does not commit an out-of-range height on unmount', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const setCameraHeight = vi.fn();
    const user = userEvent.setup();

    const { unmount } = render(
      <Settings {...baseProps} setCameraHeight={setCameraHeight} />,
    );

    const input = screen.getByLabelText(/camera height/i);
    await user.clear(input);
    await user.type(input, '50'); // below the 100 mm floor

    unmount();

    expect(setCameraHeight).not.toHaveBeenCalled();
  });
});

describe('Settings model metadata', () => {
  it('renders live registry values when /api/metadata succeeds', async () => {
    // Distinctive server values prove the live data wins over the constants.
    stubFetchRoutes({
      metadata: () =>
        Promise.resolve({
          ok: true,
          json: async () => ({
            model: {
              version: 'v9.9.9',
              architecture: 'YOLOv8x (server)',
              parameters: '68M',
              weights_file: 'model-v9.9.9.pt',
              verified: true,
              metrics: { map50: 0.5, mean_iou: 0.4, test_set_size: 10 },
            },
          }),
        }),
    });

    render(<Settings {...baseProps} />);

    expect(await screen.findByText('v9.9.9')).toBeInTheDocument();
    expect(screen.getByText('YOLOv8x (server)')).toBeInTheDocument();
    expect(screen.getByText('0.5')).toBeInTheDocument();
    expect(
      screen.getByText(/model-v9\.9\.9\.pt \(verified\)/),
    ).toBeInTheDocument();
    // The constants are replaced, not rendered alongside the live values.
    expect(screen.queryByText(MODEL_INFO.architecture)).not.toBeInTheDocument();
  });

  it('falls back to MODEL_INFO constants when /api/metadata fails', async () => {
    // The client logs the failure in dev; keep the test output clean.
    vi.spyOn(console, 'error').mockImplementation(() => {});
    stubFetchRoutes({
      metadata: () =>
        Promise.resolve({
          ok: false,
          status: 503,
          headers: { get: () => null },
          json: async () => ({}),
        }),
    });

    render(<Settings {...baseProps} />);

    // Version has no baked-in fallback on purpose - it reads 'unknown'.
    expect(await screen.findByText('unknown')).toBeInTheDocument();
    expect(screen.getByText(MODEL_INFO.architecture)).toBeInTheDocument();
    expect(screen.getByText(MODEL_INFO.weights)).toBeInTheDocument();
  });
});

describe('Settings toggle switches (a11y)', () => {
  beforeEach(() => {
    // Health fetch never resolves; we only exercise the toggles here.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  });

  it('exposes the dark-mode toggle as a switch reflecting its state', () => {
    const { rerender } = render(<Settings {...baseProps} darkMode={false} />);

    expect(
      screen.getByRole('switch', { name: /dark mode/i }),
    ).toHaveAttribute('aria-checked', 'false');

    rerender(<Settings {...baseProps} darkMode={true} />);
    expect(
      screen.getByRole('switch', { name: /dark mode/i }),
    ).toHaveAttribute('aria-checked', 'true');
  });

  it('exposes the leaf-filter toggle as a switch reflecting its state', () => {
    const { rerender } = render(
      <Settings {...baseProps} aspectRatioFilter={true} />,
    );

    expect(
      screen.getByRole('switch', { name: /leaf filter/i }),
    ).toHaveAttribute('aria-checked', 'true');

    rerender(<Settings {...baseProps} aspectRatioFilter={false} />);
    expect(
      screen.getByRole('switch', { name: /leaf filter/i }),
    ).toHaveAttribute('aria-checked', 'false');
  });
});
