// Tests for the shared API client: success parsing, the ok-check before
// JSON parsing, error-message building (detail + request-id ref), and the
// pass-through of AbortError.

import { detectImage, getHealth, ApiError } from './client.js';

// Build a minimal fetch Response stand-in.
function fakeResponse(body, { ok = true, status = 200, headers = {} } = {}) {
  return {
    ok,
    status,
    headers: { get: (key) => headers[key] ?? null },
    json: async () => body,
  };
}

beforeEach(() => {
  // The client logs failures via console.error in dev; silence it so the
  // error-path tests don't print noise.
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('detectImage', () => {
  it('returns parsed JSON on a successful response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse({ count: 3 })));

    await expect(detectImage(new FormData())).resolves.toEqual({ count: 3 });
  });

  it('throws with the detail and request-id ref on a non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        fakeResponse(
          { detail: 'bad image' },
          { ok: false, status: 400, headers: { 'X-Request-ID': 'abc123' } },
        ),
      ),
    );

    await expect(detectImage(new FormData())).rejects.toThrow(
      /bad image \(ref: abc123\)/,
    );
  });

  it('falls back to the status when the error body has no detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse({}, { ok: false, status: 503 })),
    );

    await expect(detectImage(new FormData())).rejects.toThrow(/Server returned 503/);
  });

  it('rethrows an AbortError untouched', async () => {
    const abortErr = Object.assign(new Error('aborted'), { name: 'AbortError' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortErr));

    await expect(detectImage(new FormData())).rejects.toMatchObject({
      name: 'AbortError',
    });
  });
});

describe('getHealth', () => {
  it('returns parsed JSON on a successful response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse({ status: 'ok', model_loaded: true })),
    );

    await expect(getHealth()).resolves.toEqual({
      status: 'ok',
      model_loaded: true,
    });
  });

  it('checks response.ok and throws an ApiError instead of returning the body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        fakeResponse({ detail: 'unhealthy' }, { ok: false, status: 503 }),
      ),
    );

    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});
