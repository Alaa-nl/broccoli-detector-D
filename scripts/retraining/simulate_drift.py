#!/usr/bin/env python3
"""Push the functional ML metrics into "drifted" territory, on demand.

Generates synthetic "bad field condition" images - near-black sensor noise
and low-contrast green blobs, the kind of frames a camera produces at dusk or
through fog - and POSTs them to /api/detect. The model finds little or
nothing in them, so on the dashboard the mean detection confidence sinks and
the empty-result rate climbs: exactly the situation triggers T1 and T2 in
check_triggers.py are watching for. This makes the retraining scenario
demoable end-to-end without waiting for a real bad day in the field.

Dependencies: Pillow only (any python with it works: pip install pillow).
The HTTP side is deliberately stdlib (hand-built multipart body with a uuid
boundary) so `requests` isn't needed.

Rate limiting: the backend throttles /api/detect per client IP
(RATE_LIMIT_MAX, default 10 per 60s). The default --delay of 1.2s outruns
that, so for a smooth demo either start the backend with a raised limit
(e.g. RATE_LIMIT_MAX=60) or run with --delay 6. When a 429 does come back
the script honours Retry-After and retries, so it always completes - just
slower.
"""

import argparse
import io
import json
import random
import sys
import time
import urllib.error
import urllib.request
import uuid

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    print(
        "Pillow is required for image generation: pip install pillow",
        file=sys.stderr,
    )
    sys.exit(2)

DEFAULT_URL = "http://localhost:8080/api/detect"
SIZE = (640, 480)


def make_dark_noise(rng):
    """Near-black sensor noise: a frame shot at dusk with no flash.

    No green, no shapes - the model should find nothing, which feeds the
    empty-result counter directly.
    """
    sigma = rng.randint(40, 80)
    noise = Image.effect_noise(SIZE, sigma)
    # Crush the brightness to the bottom ~16% of the range; pure black would
    # be suspicious, dark mush is what real underexposed frames look like.
    return noise.point(lambda v: v // 6).convert("RGB")


def make_green_blobs(rng):
    """Low-contrast green blobs: foliage in fog, no crown texture.

    Greenish enough to look like a field, but blurred and flat so any boxes
    the model does produce come out at low confidence - this is what drags
    the mean-confidence metric down.
    """
    base = (38, 52, 36)
    img = Image.new("RGB", SIZE, base)
    draw = ImageDraw.Draw(img)
    for _ in range(rng.randint(4, 9)):
        cx = rng.randint(0, SIZE[0])
        cy = rng.randint(0, SIZE[1])
        r = rng.randint(25, 70)
        shade = (
            base[0] + rng.randint(4, 16),
            base[1] + rng.randint(4, 16),
            base[2] + rng.randint(2, 10),
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=shade)
    return img.filter(ImageFilter.GaussianBlur(radius=8))


GENERATORS = [
    ("dark-noise", make_dark_noise),
    ("green-blobs", make_green_blobs),
]


def encode_multipart(filename, jpeg_bytes):
    """Build a multipart/form-data body by hand (stdlib has no helper)."""
    boundary = uuid.uuid4().hex
    body = b"".join([
        "--{0}\r\n".format(boundary).encode(),
        'Content-Disposition: form-data; name="file"; '
        'filename="{0}"\r\n'.format(filename).encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        jpeg_bytes,
        "\r\n--{0}--\r\n".format(boundary).encode(),
    ])
    return body, "multipart/form-data; boundary={0}".format(boundary)


def post_image(url, filename, jpeg_bytes, timeout_s=60.0):
    """POST one image; returns (http_status, parsed_json_or_None).

    Honours Retry-After on 429 so the run survives the backend rate limiter
    instead of dying halfway through a demo.
    """
    body, content_type = encode_multipart(filename, jpeg_bytes)
    for _ in range(5):
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                return exc.code, None
            wait = exc.headers.get("Retry-After")
            wait_s = float(wait) if wait and wait.isdigit() else 5.0
            print(
                "      rate limited (429), waiting {0:.0f}s "
                "(raise RATE_LIMIT_MAX on the backend to avoid "
                "this)".format(wait_s)
            )
            time.sleep(wait_s)
    return 429, None


def main():
    parser = argparse.ArgumentParser(
        description="Send synthetic bad-field-condition images to "
                    "/api/detect so the drift triggers have something "
                    "to fire on.",
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Detect endpoint (default %(default)s - the nginx frontend, "
             "which injects the X-API-Key server-side; point at the backend "
             "directly only when no API_KEY is set)",
    )
    parser.add_argument(
        "--count", type=int, default=30,
        help="Number of images to send (default %(default)s)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.2,
        help="Seconds between requests (default %(default)s); see the "
             "rate-limit note in the module docstring",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Seed the RNG for a reproducible image sequence",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    ok = empty = failed = 0
    crowns_seen = 0

    for i in range(1, args.count + 1):
        kind, generator = GENERATORS[i % len(GENERATORS)]
        img = generator(rng)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        filename = "drift_{0}_{1:03d}.jpg".format(kind, i)

        try:
            status, payload = post_image(args.url, filename, buf.getvalue())
        except (urllib.error.URLError, OSError) as exc:
            print(
                "\nCould not reach {0}: {1}\n"
                "Is the stack running? Start it with: docker compose up "
                "--build  (frontend on :8080)".format(args.url, exc),
                file=sys.stderr,
            )
            sys.exit(2)

        if status == 200 and payload is not None:
            ok += 1
            crowns = payload.get("num_crowns", 0)
            crowns_seen += crowns
            if crowns == 0:
                empty += 1
            print("[{0:>2}/{1}] {2:<11} HTTP 200  crowns={3}  "
                  "inference={4:.0f}ms".format(
                      i, args.count, kind, crowns,
                      payload.get("inference_time_ms", 0.0)))
        else:
            failed += 1
            print("[{0:>2}/{1}] {2:<11} HTTP {3}  (request failed)".format(
                i, args.count, kind, status))

        if i < args.count:
            time.sleep(args.delay)

    print()
    print("Done: {0} sent, {1} ok, {2} empty results, {3} failed.".format(
        args.count, ok, empty, failed))
    if ok:
        print("Mean crowns per accepted image: {0:.2f}".format(
            crowns_seen / ok))
    print()
    print("Expected movement on the dashboard over the query window:")
    print("  - broccoli_detection_confidence: mean drops (T1 watches this)")
    print("  - broccoli_empty_detections_total / "
          "broccoli_detection_requests_total: empty rate climbs (T2)")
    print("  - broccoli_detections_per_image: mass piles up in the 0 bucket")
    print()
    print("Now run:  python3 scripts/retraining/check_triggers.py "
          "--window 15m")


if __name__ == "__main__":
    main()
