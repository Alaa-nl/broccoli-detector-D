"""Prometheus metrics: operational (HTTP, inference) and functional (ML).

Why these specific metrics:

  Operational - request rate/latency/error-rate plus the default process_*
  collectors cover "is the service healthy and fast enough on a small
  instance", the questions that matter for a CPU-bound model on a
  fractional-vCPU plan.

  Functional - the model has no ground truth in production, so drift has to
  be inferred from prediction distributions: confidence (drops when field
  conditions diverge from the training set), crowns-per-image and the
  empty-result rate (spikes when the threshold or model no longer fits the
  scene), and crown diameter (shifts with season, camera height misuse, or
  genuine crop change). The retraining triggers in scripts/retraining/
  consume exactly these series.

Functional metrics are recorded only for completed detections - a failed
request says nothing about the model, and the HTTP counters already track
failures. Everything lives in the default registry, which is safe because
the app deliberately runs as a single process (see backend/Dockerfile).
"""

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Info,
    generate_latest,
)

# --- Operational ----------------------------------------------------------

HTTP_REQUESTS = Counter(
    "broccoli_http_requests_total",
    "HTTP requests handled, by method, normalised path and status code.",
    ["method", "path", "status"],
)

HTTP_DURATION = Histogram(
    "broccoli_http_request_duration_seconds",
    "HTTP request latency, by method and normalised path.",
    ["method", "path"],
    # Wide range: /api/health is sub-millisecond while /api/detect on a
    # fractional vCPU can take tens of seconds.
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)

INFERENCE_DURATION = Histogram(
    "broccoli_inference_duration_seconds",
    "Pure YOLO inference time per image (excludes upload, drawing, I/O).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)

APP_INFO = Info(
    "broccoli_app",
    "Static build/deploy identity labels for the running instance.",
)

# --- Functional (ML) --------------------------------------------------------

DETECTION_REQUESTS = Counter(
    "broccoli_detection_requests_total",
    "Completed /api/detect requests (denominator for the empty-result rate).",
)

EMPTY_DETECTIONS = Counter(
    "broccoli_empty_detections_total",
    "Completed detections that found zero crowns after filtering.",
)

DETECTIONS_PER_IMAGE = Histogram(
    "broccoli_detections_per_image",
    "Crowns found per image (after the leaf filter).",
    buckets=(0, 1, 2, 3, 4, 5, 8, 12, 20, 50),
)

DETECTION_CONFIDENCE = Histogram(
    "broccoli_detection_confidence",
    "Model confidence of each kept detection (distribution drift signal).",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)

CROWN_DIAMETER_MM = Histogram(
    "broccoli_crown_diameter_mm",
    "Estimated crown diameter in mm (seasonal / calibration drift signal).",
    buckets=(20, 40, 60, 80, 100, 130, 160, 200, 300, 500),
)

FILTERED_BOXES = Counter(
    "broccoli_filtered_boxes_total",
    "Boxes removed by the aspect-ratio (leaf) filter.",
)


# Routes are a small fixed set, so label by route - but anything unknown
# collapses to "other" and /uploads/* is collapsed to one value, keeping
# label cardinality bounded no matter what clients request.
_KNOWN_PATHS = {
    "/",
    "/api/health",
    "/api/ready",
    "/api/metadata",
    "/api/detect",
    "/metrics",
}


def _normalise_path(path: str) -> str:
    if path in _KNOWN_PATHS:
        return path
    if path.startswith("/uploads/"):
        return "/uploads/*"
    return "other"


def set_app_info(
    app_version: str, model_version: str, deploy_env: str, git_sha: str
) -> None:
    """Publish the instance identity once at startup."""
    APP_INFO.info({
        "app_version": app_version,
        "model_version": model_version,
        "deploy_env": deploy_env,
        "git_sha": git_sha,
    })


def record_detection(
    num_crowns: int,
    confidences: list,
    diameters_mm: list,
    num_filtered: int,
    inference_seconds: float,
) -> None:
    """Record the functional metrics for one completed detection."""
    DETECTION_REQUESTS.inc()
    INFERENCE_DURATION.observe(inference_seconds)
    DETECTIONS_PER_IMAGE.observe(num_crowns)
    if num_crowns == 0:
        EMPTY_DETECTIONS.inc()
    if num_filtered > 0:
        FILTERED_BOXES.inc(num_filtered)
    for confidence in confidences:
        DETECTION_CONFIDENCE.observe(confidence)
    for diameter in diameters_mm:
        CROWN_DIAMETER_MM.observe(diameter)


def render_metrics() -> tuple:
    """Serialised metrics for the /metrics endpoint: (payload, content_type)."""
    return generate_latest(), CONTENT_TYPE_LATEST


class MetricsMiddleware:
    """ASGI middleware that counts and times every HTTP request.

    Sits just inside RequestIDMiddleware so that requests which blow up
    before producing a response are still counted: the finally block
    records the default 500 and RequestIDMiddleware (outside) then sends
    the actual 500 body. Responses synthesised by inner middleware (e.g.
    the 413 from BodySizeLimitMiddleware) pass through send and are
    counted with their real status.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = _normalise_path(scope["path"])
        # Assume 500 until a response actually starts - an exception that
        # escapes the app would otherwise go uncounted.
        status = "500"
        start = time.monotonic()

        async def send_with_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = str(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            HTTP_DURATION.labels(method, path).observe(time.monotonic() - start)
            HTTP_REQUESTS.labels(method, path, status).inc()
