// Tests for the Upload page's abort/timeout behaviour.

import { render, screen, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Upload from './Upload.jsx';
import {
  ACCEPT,
  ALLOWED_TYPES,
  MAX_FILE_SIZE_MB,
  TYPE_LABELS,
} from '../constants/upload.js';

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

const pngFile = (name = 'broccoli.png') =>
  new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' });

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

describe('Upload drop-zone accessibility', () => {
  it('exposes the file input via its drop-zone label and keeps it focusable', () => {
    renderUpload();

    // The input is associated with the label, so assistive tech announces it.
    const input = screen.getByLabelText(/drag & drop/i);
    expect(input).toHaveAttribute('type', 'file');

    // sr-only keeps it in the tab order (unlike `hidden`, which is display:none).
    expect(input).toHaveClass('sr-only');
    expect(input).not.toHaveClass('hidden');
  });
});

describe('Upload validation constants are single-sourced', () => {
  it('derives the accept attribute and format chips from the constants', () => {
    renderUpload();

    const input = screen.getByLabelText(/drag & drop/i);
    expect(input).toHaveAttribute('accept', ACCEPT);

    // One chip per allowed type label, plus the size limit chip.
    ALLOWED_TYPES.forEach((type) => {
      expect(screen.getByText(TYPE_LABELS[type])).toBeInTheDocument();
    });
    expect(screen.getByText(`Max ${MAX_FILE_SIZE_MB} MB`)).toBeInTheDocument();
  });
});

describe('Upload object URL lifecycle', () => {
  let revokeSpy;

  beforeEach(() => {
    // Distinct URLs per createObjectURL call so we can assert which one is
    // revoked. Scoped to this block, so the abort/timeout tests are unaffected.
    let n = 0;
    URL.createObjectURL = vi.fn(() => `blob:url-${++n}`);
    revokeSpy = vi.fn();
    URL.revokeObjectURL = revokeSpy;
  });

  it('revokes the previous preview URL when a new file is chosen', async () => {
    const user = userEvent.setup();
    const { container } = renderUpload();
    const input = container.querySelector('input[type="file"]');

    await user.upload(input, pngFile('a.png')); // -> blob:url-1
    await user.upload(input, pngFile('b.png')); // -> blob:url-2, revokes url-1

    expect(revokeSpy).toHaveBeenCalledWith('blob:url-1');
  });

  it('revokes the preview URL on unmount', async () => {
    const user = userEvent.setup();
    const { container, unmount } = renderUpload();

    await user.upload(container.querySelector('input[type="file"]'), pngFile()); // url-1
    unmount();

    expect(revokeSpy).toHaveBeenCalledWith('blob:url-1');
  });
});

describe('Upload error announcement (a11y)', () => {
  it('surfaces the error inside a role="alert" live region', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', hangingFetch());

    const { container } = renderUpload();
    await user.upload(container.querySelector('input[type="file"]'), pngFile());
    await user.click(screen.getByRole('button', { name: /detect broccoli/i }));

    // Cancelling sets an error; it must land in an alert region so a screen
    // reader announces it instead of leaving the user with no feedback.
    await user.click(await screen.findByRole('button', { name: /cancel/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/detection cancelled/i);
  });
});
