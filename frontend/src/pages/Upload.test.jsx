// Tests for the Upload page's abort/timeout behaviour (P5-2).

import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Upload from './Upload.jsx';

// A fetch that never resolves on its own and rejects with an AbortError
// the moment its signal is aborted - lets us drive timeout/cancel paths.
function hangingFetch() {
  return vi.fn(
    (_url, opts) =>
      new Promise((_resolve, reject) => {
        opts.signal.addEventListener('abort', () => {
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      }),
  );
}

function renderUpload() {
  return render(
    <MemoryRouter>
      <Upload
        cameraHeight={1000}
        confThreshold={0.4}
        aspectRatioFilter={true}
        onDetected={vi.fn()}
      />
    </MemoryRouter>,
  );
}

const pngFile = () =>
  new File([new Uint8Array([1, 2, 3])], 'broccoli.png', { type: 'image/png' });

afterEach(() => {
  vi.useRealTimers();
});

describe('Upload abort/timeout', () => {
  it('times out and unsticks the button when the watchdog fires', async () => {
    // Fake timers to fast-forward the 60s watchdog. Use fireEvent (synchronous)
    // here, not userEvent - userEvent's internal delays deadlock with faked
    // timers.
    vi.useFakeTimers();
    vi.stubGlobal('fetch', hangingFetch());

    const { container } = renderUpload();
    fireEvent.change(container.querySelector('input[type="file"]'), {
      target: { files: [pngFile()] },
    });
    fireEvent.click(screen.getByRole('button', { name: /detect broccoli/i }));

    // Mid-request: button is in the loading state.
    expect(
      screen.getByRole('button', { name: /detecting/i }),
    ).toBeInTheDocument();

    // Advance past the 60s watchdog -> abort -> timeout message.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60001);
    });

    expect(screen.getByText(/timed out/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /detect broccoli/i }),
    ).toBeInTheDocument();
  });

  it('cancels an in-flight detection and re-enables the button', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', hangingFetch());

    const { container } = renderUpload();
    await user.upload(container.querySelector('input[type="file"]'), pngFile());
    await user.click(screen.getByRole('button', { name: /detect broccoli/i }));

    // Cancel button appears only while detecting.
    const cancelBtn = await screen.findByRole('button', { name: /cancel/i });
    await user.click(cancelBtn);

    expect(await screen.findByText(/detection cancelled/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /detect broccoli/i }),
    ).toBeInTheDocument();
  });
});
