"""
FastAPI main entry point for the Broccoli Crown Detection app.

This file starts the API server and connects all the routes.
The YOLOv8n model is loaded one time at startup, so the server
does not need to load it again for every request.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import detect, health
from app.services.detector import BroccoliDetector


# Path to the trained YOLOv8n weights file.
# In Deliverable B we trained the model and saved best.pt here.
WEIGHTS_PATH = Path(__file__).parent.parent / "weights" / "best.pt"

# Folder where uploaded images are saved.
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Retention policy for saved uploads/annotated images. Without a
# sweep the uploads dir grows forever and every field photo stays publicly
# downloadable indefinitely. We delete files older than UPLOAD_TTL_SECONDS,
# checking every UPLOAD_SWEEP_SECONDS. The TTL is far longer than a request
# so the frontend can still fetch /uploads/... after the JSON response.
UPLOAD_TTL_SECONDS = int(os.getenv("UPLOAD_TTL_SECONDS", "3600"))      # 60 min
UPLOAD_SWEEP_SECONDS = int(os.getenv("UPLOAD_SWEEP_SECONDS", "600"))   # 10 min

# Hard cap on the size of any incoming request body. nginx already caps
# the proxied path (client_max_body_size 15M), but a client can reach the
# backend directly, so we enforce the same bound here independent of the
# proxy. 15 MB leaves headroom above the 10 MB image limit for multipart
# boundaries and the form fields.
MAX_REQUEST_BODY_BYTES = 15 * 1024 * 1024  # 15 MB

# CORS origins allowed to call the API from a browser. Comma-separated,
# overridable via env. Defaults cover local dev (Vite :5173, compose :8080).
# The deployed app calls the backend same-origin through the proxy, so CORS
# is not exercised there; set this only if a browser must call the backend
# cross-origin directly.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:8080",
    ).split(",")
    if origin.strip()
]


async def _retention_sweep(upload_dir: Path, ttl: int, interval: int):
    """Periodically delete saved images older than `ttl` seconds.

    Runs forever as a background task until cancelled at shutdown. Skips
    dotfiles (so uploads/.gitkeep survives) and swallows per-file errors
    (e.g. a file removed by a concurrent request) so one bad file cannot
    kill the loop.
    """
    while True:
        try:
            now = time.time()
            for path in upload_dir.iterdir():
                if path.name.startswith("."):
                    continue
                try:
                    if path.is_file() and now - path.stat().st_mtime > ttl:
                        path.unlink(missing_ok=True)
                except OSError:
                    # File vanished or is momentarily unreadable; skip it.
                    continue
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            print(f"WARNING: retention sweep failed: {exc}")
        await asyncio.sleep(interval)


class _BodyTooLarge(Exception):
    """Raised internally when a streamed request body exceeds the cap."""


class BodySizeLimitMiddleware:
    """Pure-ASGI middleware that rejects oversized request bodies with 413.

    Two layers:
      1. Fast path - trust the Content-Length header when present and
         reject before reading a single byte of the body.
      2. Backstop - for chunked / missing-length requests, count the body
         bytes as they stream in and abort once the cap is exceeded.

    This bounds memory independent of nginx and complements the route's
    own streaming size check in ImageUploader.save().
    """

    def __init__(self, app, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: trust Content-Length when the client sends it.
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_size:
                    await self._send_413(send)
                    return
            except ValueError:
                pass  # Malformed header; fall through to the byte counter.

        # Backstop: count bytes as the body streams in.
        total = 0
        response_started = False

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_size:
                    raise _BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _BodyTooLarge:
            # Only safe to send our own response if the app has not
            # already started one.
            if not response_started:
                await self._send_413(send)

    @staticmethod
    async def _send_413(send):
        body = json.dumps({"detail": "Request body too large."}).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler.

    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.
    """
    # Load the YOLOv8n model into memory one time.
    # We store it on app.state so any route can use it.
    print(f"Loading YOLOv8n model from: {WEIGHTS_PATH}")
    app.state.detector = BroccoliDetector(weights_path=str(WEIGHTS_PATH))

    # Fail fast in production: if the model did not load (best.pt missing),
    # refuse to boot so a misconfigured deploy crashes loudly instead of
    # serving 503s forever. Frontend devs can set ALLOW_MISSING_WEIGHTS=1
    # to run the UI without the weights file.
    allow_missing = os.getenv("ALLOW_MISSING_WEIGHTS", "").lower() in ("1", "true", "yes")
    if not app.state.detector.is_ready() and not allow_missing:
        raise RuntimeError(
            f"YOLO model failed to load from {WEIGHTS_PATH}. "
            f"Set ALLOW_MISSING_WEIGHTS=1 to start without it (frontend dev only)."
        )

    if app.state.detector.is_ready():
        print("Model loaded. API is ready.")
    else:
        print(
            "WARNING: API started WITHOUT a model (ALLOW_MISSING_WEIGHTS set). "
            "Detections will return 503 until best.pt is present."
        )

    # Start the background sweep that deletes old uploaded/annotated images
    # so the disk cannot grow without bound.
    sweep_task = asyncio.create_task(
        _retention_sweep(UPLOAD_DIR, UPLOAD_TTL_SECONDS, UPLOAD_SWEEP_SECONDS)
    )
    print(
        f"Upload retention sweep started "
        f"(ttl={UPLOAD_TTL_SECONDS}s, interval={UPLOAD_SWEEP_SECONDS}s)."
    )

    yield

    # Stop the background sweep cleanly on shutdown.
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    print("API is shutting down.")


# Create the FastAPI app and pass the lifespan handler.
app = FastAPI(
    title="Broccoli Crown Detection API",
    description="A small API that finds broccoli crowns in field images "
                "and estimates the size of each crown.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the React frontend to call this API from a browser. Origins come
# from CORS_ALLOW_ORIGINS (see above). We never combine a wildcard origin
# with credentials (spec-forbidden), and since nothing uses cookies or an
# Authorization header, credentials stay off. The X-API-Key header is
# injected by the nginx proxy server-side, so the browser only needs to
# send Content-Type (for the multipart upload).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Reject oversized request bodies before they are buffered. Added last so
# it wraps the others and runs first on each incoming request.
app.add_middleware(BodySizeLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)

# Serve uploaded and result images as static files so the frontend can show them.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Connect the route files.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(detect.router, prefix="/api", tags=["detect"])


@app.get("/")
def root():
    """Simple welcome message at the root URL."""
    return {
        "message": "Broccoli Crown Detection API is running.",
        "docs": "/docs",
    }
