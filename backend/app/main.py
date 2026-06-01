"""
FastAPI main entry point for the Broccoli Crown Detection app.

This file starts the API server and connects all the routes.
The YOLOv8n model is loaded one time at startup, so the server
does not need to load it again for every request.
"""

import asyncio
import contextvars
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import detect, health
from app.services.detector import BroccoliDetector


# Per-request correlation id. Each incoming request gets a short id (echoed
# from a well-formed inbound X-Request-ID header, or freshly generated) that
# we stash in a ContextVar so the route, the logging filter, and the request-id
# middleware all read the same value without passing it around. The "-" default
# is what shows for logs emitted outside any request (startup, the retention
# sweep, shutdown).
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# Only echo an inbound X-Request-ID if it is well-formed. This blocks log
# forging / header injection (newlines, control chars) and bounds the length;
# anything else is replaced with a freshly generated id.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class _RequestIDLogFilter(logging.Filter):
    """Stamp the current request id onto every log record.

    The log format includes [%(request_id)s], so every record must carry a
    request_id attribute or formatting would raise. This filter sets it from
    the ContextVar (default "-" outside a request), so even library/uvicorn
    records that reach the root handler format cleanly.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


# Configure logging once for the whole app. Level is overridable via
# LOG_LEVEL (default INFO). Using the logging module (instead of print)
# gives levels/timestamps/logger names and lets logs be filtered or routed
# without code changes. The [%(request_id)s] field ties each line to one
# request (see RequestIDMiddleware). Output still goes to stdout, so
# Docker/Render log capture is unchanged.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)
# Attach the filter to the root handler(s) basicConfig just created, so every
# record formatted there carries a request_id (no KeyError on library logs).
_rid_filter = _RequestIDLogFilter()
for _handler in logging.getLogger().handlers:
    if not any(isinstance(f, _RequestIDLogFilter) for f in _handler.filters):
        _handler.addFilter(_rid_filter)

logger = logging.getLogger(__name__)


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

# When DEPLOY_ENV=production, hide the interactive API docs and OpenAPI
# schema so the public backend does not advertise its endpoints. Local dev
# and docker compose leave it unset (dev), keeping /docs available.
DEPLOY_ENV = os.getenv("DEPLOY_ENV", "dev")
_is_prod = DEPLOY_ENV.strip().lower() == "production"

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
            logger.warning("Retention sweep failed: %s", exc)
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


class RequestIDMiddleware:
    """Pure-ASGI middleware that gives every request a correlation id.

    For each HTTP request it:
      1. Picks an id - echoing a well-formed inbound X-Request-ID, else a
         fresh uuid4 hex.
      2. Publishes it in request_id_ctx so the route, the logging filter and
         this middleware all see the same value; resets it in a finally so it
         cannot leak into the next request.
      3. Stamps it back as the X-Request-ID response header on every response.
      4. Catches any UNHANDLED exception from the inner app and returns a safe
         JSON 500 ({"detail", "request_id"}) carrying the header, logged once
         with a traceback. We handle it HERE rather than via
         @app.exception_handler because Starlette runs the catch-all Exception
         handler in its outer ServerErrorMiddleware - outside this middleware -
         where the header would be missing and the id already reset.

    Registered OUTERMOST (added last), so it wraps the body-size and CORS
    middleware and every response (including a 413) carries the header.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Pick the id: trust an inbound header only when it is well-formed.
        headers = dict(scope.get("headers", []))
        inbound = headers.get(b"x-request-id")
        request_id = None
        if inbound is not None:
            candidate = inbound.decode("latin-1", "replace")
            if _REQUEST_ID_RE.fullmatch(candidate):
                request_id = candidate
        if request_id is None:
            request_id = uuid.uuid4().hex
        request_id_bytes = request_id.encode("ascii")

        token = request_id_ctx.set(request_id)
        response_started = False

        async def send_with_request_id(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                # Replace any existing X-Request-ID, then add exactly one.
                # (headers is a list of lowercase (bytes, bytes) tuples.)
                headers_out = [
                    (k, v)
                    for (k, v) in message.get("headers", [])
                    if k.lower() != b"x-request-id"
                ]
                headers_out.append((b"x-request-id", request_id_bytes))
                message = {**message, "headers": headers_out}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # An unhandled error escaped the app. Log it once, with the id and
            # a traceback. HTTPException / validation errors never reach here -
            # Starlette's ExceptionMiddleware turns those into normal responses
            # further in, so only genuinely unexpected failures land here.
            logger.exception("Unhandled error while handling request [%s]", request_id)
            if response_started:
                # Headers already sent; we cannot emit a clean 500. Re-raise so
                # the server tears the connection down.
                raise
            body = json.dumps(
                {"detail": "Internal server error", "request_id": request_id}
            ).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-request-id", request_id_bytes),
                ],
            })
            await send({"type": "http.response.body", "body": body})
        finally:
            request_id_ctx.reset(token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler.

    Code before 'yield' runs at startup.
    Code after 'yield' runs at shutdown.
    """
    # Load the YOLOv8n model into memory one time.
    # We store it on app.state so any route can use it.
    logger.info("Loading YOLOv8n model from: %s", WEIGHTS_PATH.name)
    app.state.detector = BroccoliDetector(weights_path=str(WEIGHTS_PATH))

    # Fail fast in production: if the model did not load (best.pt missing),
    # refuse to boot so a misconfigured deploy crashes loudly instead of
    # serving 503s forever. Frontend devs can set ALLOW_MISSING_WEIGHTS=1
    # to run the UI without the weights file.
    allow_missing = os.getenv("ALLOW_MISSING_WEIGHTS", "").lower() in ("1", "true", "yes")
    if not app.state.detector.is_ready() and not allow_missing:
        raise RuntimeError(
            f"YOLO model failed to load from {WEIGHTS_PATH.name}. "
            f"Set ALLOW_MISSING_WEIGHTS=1 to start without it (frontend dev only)."
        )

    if app.state.detector.is_ready():
        logger.info("Model loaded. API is ready.")
    else:
        logger.warning(
            "API started WITHOUT a model (ALLOW_MISSING_WEIGHTS set). "
            "Detections will return 503 until best.pt is present."
        )

    # Start the background sweep that deletes old uploaded/annotated images
    # so the disk cannot grow without bound.
    sweep_task = asyncio.create_task(
        _retention_sweep(UPLOAD_DIR, UPLOAD_TTL_SECONDS, UPLOAD_SWEEP_SECONDS)
    )
    logger.info(
        "Upload retention sweep started (ttl=%ss, interval=%ss).",
        UPLOAD_TTL_SECONDS,
        UPLOAD_SWEEP_SECONDS,
    )

    yield

    # Stop the background sweep cleanly on shutdown.
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    logger.info("API is shutting down.")


# Create the FastAPI app and pass the lifespan handler.
app = FastAPI(
    title="Broccoli Crown Detection API",
    description="A small API that finds broccoli crowns in field images "
                "and estimates the size of each crown.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
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

# Reject oversized request bodies before they are buffered.
app.add_middleware(BodySizeLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES)

# Assign a correlation id to every request. Added LAST so it is the OUTERMOST
# middleware: it runs first on the way in (the id is set before anything else
# can fail) and last on the way out (its send-wrapper stamps X-Request-ID onto
# every response, including the 413 from BodySizeLimitMiddleware and CORS
# responses). This registration must stay last - the ordering is load-bearing.
app.add_middleware(RequestIDMiddleware)

# Serve uploaded and result images as static files so the frontend can show them.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Connect the route files.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(detect.router, prefix="/api", tags=["detect"])


@app.get("/")
def root():
    """Simple welcome message at the root URL."""
    info = {"message": "Broccoli Crown Detection API is running."}
    # Only advertise the docs when they are actually enabled (dev).
    if not _is_prod:
        info["docs"] = "/docs"
    return info
