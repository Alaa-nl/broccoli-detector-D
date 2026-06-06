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

  it('throws an ApiError with the status when the error body has no detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse({}, { ok: false, status: 503 })),
    );

    await expect(detectImage(new FormData())).rejects.toBeInstanceOf(ApiError);
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

  it('returns the degraded body on a 503 (backend up, model not loaded)', async () => {
    // /health signals "degraded" with HTTP 503 + a JSON body; that body is
    // meaningful, so getHealth returns it rather than treating it as a failure.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        fakeResponse(
          { status: 'degraded', model_loaded: false },
          { ok: false, status: 503 },
        ),
      ),
    );

    await expect(getHealth()).resolves.toEqual({
      status: 'degraded',
      model_loaded: false,
    });
  });

  it('rethrows an AbortError untouched', async () => {
    const abortErr = Object.assign(new Error('aborted'), { name: 'AbortError' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortErr));

    await expect(getHealth()).rejects.toMatchObject({ name: 'AbortError' });
  });
});
