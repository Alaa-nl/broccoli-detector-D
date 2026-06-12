"""FastAPI entry point: app config, middleware, lifespan, route wiring."""

import asyncio
import contextvars
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import detect, health, metadata
from app.services import model_store
from app.services.detector import BroccoliDetector
from app.services.metrics import MetricsMiddleware, render_metrics, set_app_info


# Per-request id, shared via ContextVar so route, log filter, and middleware
# all see the same value. "-" appears on logs emitted outside any request
# (startup, retention sweep, shutdown).
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

# Well-formed inbound X-Request-ID only; blocks header injection (newlines,
# control chars) and caps length. Anything else gets a fresh id.
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")


class _RequestIDLogFilter(logging.Filter):
    """Stamps request_id onto every log record so [%(request_id)s] never KeyErrors.

    Reads from the ContextVar; library/uvicorn records get "-".
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


# App-wide logging config. Level via LOG_LEVEL (default INFO). The
# [%(request_id)s] field ties each line to one request.
logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)
# Attach to the root handler(s) so library log records also carry request_id.
_rid_filter = _RequestIDLogFilter()
for _handler in logging.getLogger().handlers:
    if not any(isinstance(f, _RequestIDLogFilter) for f in _handler.filters):
        _handler.addFilter(_rid_filter)

logger = logging.getLogger(__name__)


# Ensure the uploads directory exists before any request can hit it.
config.UPLOAD_DIR.mkdir(exist_ok=True)


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
    """ASGI middleware that rejects oversized request bodies with 413.

    Fast path: trust Content-Length when present and reject before
    reading the body. Backstop: count bytes as they stream in for
    chunked or missing-length requests.
    """

    def __init__(self, app, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: trust Content-Length when present. If it's missing or
        # malformed, the streaming counter below is the authoritative guard.
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
    """ASGI middleware that gives every request a correlation id.

    Picks an id (echoes a well-formed inbound X-Request-ID or generates
    one), publishes it via request_id_ctx, and stamps it back as the
    X-Request-ID response header. Also catches unhandled exceptions from
    the inner app and returns a JSON 500 carrying the same id.

    Why here, not @app.exception_handler: Starlette's catch-all handler
    runs in ServerErrorMiddleware (outside this one), where the header
    would be missing and the id already reset.

    Registered LAST so it wraps every other middleware. Ordering matters,
    do not move.
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
            # Genuine unhandled errors only. HTTPException and validation
            # errors are caught earlier by Starlette's ExceptionMiddleware.
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
    """Startup and shutdown handler for the FastAPI app."""

    # Resolve MODEL_VERSION via the registry; downloads from
    # MODEL_WEIGHTS_URL when the file isn't on disk (e.g. a new version
    # rolled out as an env change, without rebuilding the image).
    weights_path, weights_source = model_store.resolve_weights()

    # Verification policy: an explicit env hash always wins; production and
    # network-fetched weights must verify (registry hash); plain local dev
    # keeps the old warn-and-skip behaviour so a freshly retrained best.pt
    # doesn't block iteration before it's registered.
    expected_sha = config.EXPECTED_WEIGHTS_SHA256
    if expected_sha is None and (config.IS_PROD or weights_source == "remote"):
        expected_sha = model_store.expected_sha256(config.MODEL_VERSION)

    logger.info(
        "Loading YOLOv8n model %s from: %s (source=%s)",
        config.MODEL_VERSION, weights_path.name, weights_source,
    )
    app.state.detector = BroccoliDetector(
        weights_path=str(weights_path), expected_sha256=expected_sha
    )
    # Exposed on app.state to avoid circular imports from routes.
    app.state.upload_dir = config.UPLOAD_DIR

    # Fail fast if weights are missing; ALLOW_MISSING_WEIGHTS=1 lets
    # frontend devs run the UI without best.pt.
    if not app.state.detector.is_ready() and not config.ALLOW_MISSING_WEIGHTS:
        raise RuntimeError(
            f"YOLO model failed to load from {weights_path.name}. "
            f"Set ALLOW_MISSING_WEIGHTS=1 to start without it (frontend dev only)."
        )

    # Model card data for /api/metadata. The hash is computed once here
    # (the file is ~6 MB) so the endpoint itself stays free of disk I/O.
    app.state.model_meta = {
        "version": config.MODEL_VERSION,
        "source": weights_source,
        "weights_file": weights_path.name if weights_path.exists() else None,
        "weights_sha256": (
            model_store.compute_sha256(weights_path)
            if app.state.detector.is_ready() else None
        ),
        "verified": expected_sha is not None and app.state.detector.is_ready(),
        "registry_entry": model_store.get_registry_entry(config.MODEL_VERSION),
    }

    # Stamp the instance identity onto the metrics so dashboards can tell
    # which code + model version produced any given series.
    set_app_info(
        app_version=config.APP_VERSION,
        model_version=config.MODEL_VERSION,
        deploy_env=config.DEPLOY_ENV,
        git_sha=config.GIT_SHA or "",
    )

    if app.state.detector.is_ready():
        logger.info("Model loaded. API is ready.")
    else:
        logger.warning(
            "API started WITHOUT a model (ALLOW_MISSING_WEIGHTS set). "
            "Detections will return 503 until best.pt is present."
        )


    sweep_task = asyncio.create_task(
        _retention_sweep(
            config.UPLOAD_DIR, config.UPLOAD_TTL_SECONDS, config.UPLOAD_SWEEP_SECONDS
        )
    )
    logger.info(
        "Upload retention sweep started (ttl=%ss, interval=%ss).",
        config.UPLOAD_TTL_SECONDS,
        config.UPLOAD_SWEEP_SECONDS,
    )

    yield

    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    logger.info("API is shutting down.")


app = FastAPI(
    title="Broccoli Crown Detection API",
    description="A small API that finds broccoli crowns in field images "
                "and estimates the size of each crown.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if config.IS_PROD else "/docs",
    redoc_url=None if config.IS_PROD else "/redoc",
    openapi_url=None if config.IS_PROD else "/openapi.json",
)

# CORS for the React frontend. Credentials off (no cookies/auth headers
# used). X-API-Key is injected by nginx server-side, so browsers only
# need to send Content-Type.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Reject oversized request bodies before they are buffered.
app.add_middleware(BodySizeLimitMiddleware, max_body_size=config.MAX_REQUEST_BODY_BYTES)

# Count and time every request (Prometheus). Sits just inside RequestID so
# even requests that crash before a response are recorded as 500s.
app.add_middleware(MetricsMiddleware)

# Added LAST = outermost middleware: runs first inbound and last outbound,
# so X-Request-ID gets stamped on every response (including 413 and CORS).
# Do not move.
app.add_middleware(RequestIDMiddleware)

app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(metadata.router, prefix="/api", tags=["metadata"])
app.include_router(detect.router, prefix="/api", tags=["detect"])


@app.get("/metrics", include_in_schema=False)
def metrics():
    """Prometheus scrape endpoint.

    Not proxied by nginx (which only forwards /api/ and /uploads/), so it
    stays reachable only on the backend's own port - inside the compose
    network for the local monitoring stack, and loopback-only in the
    combined Azure container.
    """
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)


@app.get("/")
def root():
    info = {"message": "Broccoli Crown Detection API is running."}
    # Hide /docs link in production where it's also disabled.
    if not config.IS_PROD:
        info["docs"] = "/docs"
    return info
