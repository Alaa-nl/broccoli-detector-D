"""The /api/detect endpoint: upload, infer, filter, measure, annotate."""

import ipaddress
import logging
import os
import secrets
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from starlette.concurrency import run_in_threadpool

from app import config
from app.models.schemas import (
    BoundingBox,
    CrownDetection,
    DetectionResponse,
)
from app.services.annotator import draw_detections
from app.services.detection_filters import filter_by_aspect_ratio
from app.services.rate_limiter import RateLimiter
from app.services.size_estimator import SizeEstimator
from app.services.uploader import ImageUploader

logger = logging.getLogger(__name__)


# Auth (opt-in via API_KEY env var) and per-IP rate limiting. In production,
# nginx injects X-API-Key server-side so it never reaches the browser.

_rate_limiter = RateLimiter(
    config.RATE_LIMIT_MAX, config.RATE_LIMIT_WINDOW_SECONDS
)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Reject the request if API_KEY is set and the X-API-Key doesn't match.

    No-op when API_KEY is unset. Uses constant-time compare against timing.
    """
    expected = os.getenv("API_KEY")
    if not expected:
        return 
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )


def _normalise_ip(value: str) -> Optional[str]:
    """Return the canonical IP string, or None if not a valid address.

    Canonicalising collapses equivalent forms (e.g. "::1" and
    "0:0:0:0:0:0:0:1") so they don't count as separate rate-limit keys.
    """
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _client_key(request: Request) -> str:
    """Best-effort client IP for rate limiting.

    Behind nginx the real IP comes via X-Forwarded-For / X-Real-IP. Those
    headers are client-settable, so we only trust values that parse as IPs.
    Falls back to the unspoofable socket peer when no header is valid.
    """
    for header_name in ("x-forwarded-for", "x-real-ip"):
        header_value = request.headers.get(header_name)
        if not header_value:
            continue
        # X-Forwarded-For may be a comma-separated chain; the first entry is
        # the originating client.
        candidate = _normalise_ip(header_value.split(",")[0].strip())
        if candidate is not None:
            return candidate
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """Throttle CPU-heavy detection calls per client IP (429 when over)."""
    key = _client_key(request)
    if not _rate_limiter.allow(key):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please slow down and try again shortly.",
            headers={"Retry-After": str(_rate_limiter.retry_after(key))},
        )


def get_uploader() -> ImageUploader:
    """FastAPI dependency. Tests can override via app.dependency_overrides."""

    return ImageUploader(upload_dir=config.UPLOAD_DIR)


def get_size_estimator(
    camera_height_mm: float = Form(
        default=config.DEFAULT_CAMERA_HEIGHT_MM,
        ge=config.CAMERA_HEIGHT_MIN_MM,
        le=config.CAMERA_HEIGHT_MAX_MM,
        description="Camera height above the ground in mm (default 1000 mm = "
                    "1 metre). Must be between 100 and 5000 mm (inclusive).",
    ),
) -> SizeEstimator:
    """FastAPI dependency. Reads camera_height_mm from the multipart form."""

    return SizeEstimator(camera_height_mm=camera_height_mm)


# Both guards run on every route in this router. /api/health lives in a
# separate router, so monitoring stays open and unthrottled.
router = APIRouter(dependencies=[Depends(require_api_key), Depends(rate_limit)])


@router.post("/detect", response_model=DetectionResponse)
async def detect_broccoli(
    request: Request,
    file: UploadFile = File(..., description="A JPG or PNG broccoli image."),
    conf_threshold: float = Form(
        default=config.DEFAULT_CONF,
        ge=config.CONF_MIN,
        le=config.CONF_MAX,
        description="Minimum confidence (0.10-0.95). Higher = fewer false "
                    "positives but also fewer detections. Default 0.40.",
    ),
    aspect_ratio_filter: bool = Form(
        default=True,
        description="If True, drop boxes that are too elongated "
                    "(probably leaves, not crowns).",
    ),
    uploader: ImageUploader = Depends(get_uploader),
    size_estimator: SizeEstimator = Depends(get_size_estimator),
):
    """Run broccoli crown detection on an uploaded image.

    Pipeline: save → detect → leaf filter → size estimate → annotate → respond.
    """
    # --- Step 1: save the upload ---
    saved_path, image_id, pil_image = await uploader.save(file)

    img_width = pil_image.width
    img_height = pil_image.height

    # --- Step 2: run YOLO with the chosen confidence ---
    # 503 if weights didn't load at startup (model would silently return zero crowns).
    detector = request.app.state.detector
    if detector is None or not detector.is_ready():
        raise HTTPException(
            status_code=503,
            detail="The detection service is temporarily unavailable. "
                   "Please try again later.",
        )

    # Offload CPU-bound inference to a worker thread so the event loop
    # stays responsive. The detector's own lock serialises model access.
    raw_detections, inference_time_ms = await run_in_threadpool(
        detector.predict,
        pil_image,
        conf_threshold=conf_threshold,
    )
    detections_before_filter = len(raw_detections)

    # --- Step 3: optional aspect-ratio filter ---
    # Crowns are roughly square from above; elongated boxes are leaves.
    if aspect_ratio_filter:
        raw_detections = filter_by_aspect_ratio(raw_detections)

    num_filtered = detections_before_filter - len(raw_detections)

    # --- Step 4: convert each box into a CrownDetection ---
    # size_estimator is injected via Depends, configured with camera_height_mm.
    crown_models = []

    for i, det in enumerate(raw_detections, start=1):
        bbox_w_px = det["x2"] - det["x1"]
        bbox_h_px = det["y2"] - det["y1"]

        diameter_mm, diameter_cm, category = size_estimator.estimate_diameter(
            bbox_width_px=bbox_w_px,
            bbox_height_px=bbox_h_px,
            image_width_px=img_width,
        )

        crown_models.append(CrownDetection(
            crown_id=i,
            bbox=BoundingBox(
                x1=det["x1"], y1=det["y1"],
                x2=det["x2"], y2=det["y2"],
            ),
            confidence=det["confidence"],
            diameter_mm=diameter_mm,
            diameter_cm=diameter_cm,
            size_category=category,
        ))

    # --- Step 5: draw the boxes ---
    annotated_filename = f"{image_id}_annotated.jpg"
    annotated_path = config.UPLOAD_DIR / annotated_filename
    # Drawing + JPEG-encoding is blocking; offload it. The annotator wants
    # plain dicts, so derive them from the models via model_dump.
    await run_in_threadpool(
        draw_detections,
        pil_image,
        [crown.model_dump() for crown in crown_models],
        annotated_path,
    )

    # --- Step 6: build the response ---
    image_url = f"/uploads/{saved_path.name}"
    annotated_url = f"/uploads/{annotated_filename}"

    # Structured detection log; the main.py filter adds the request id.
    logger.info(
        "detection complete: image_id=%s dims=%dx%d crowns=%d filtered=%d "
        "conf=%.2f camera_height_mm=%.0f inference_ms=%.1f",
        image_id, img_width, img_height, len(crown_models), num_filtered,
        conf_threshold, size_estimator.camera_height_mm, inference_time_ms,
    )

    return DetectionResponse(
        image_id=image_id,
        image_url=image_url,
        annotated_url=annotated_url,
        image_width=img_width,
        image_height=img_height,
        crowns=crown_models,
        num_crowns=len(crown_models),
        inference_time_ms=inference_time_ms,
        camera_height_mm=size_estimator.camera_height_mm,
        conf_threshold=conf_threshold,
        aspect_ratio_filter=aspect_ratio_filter,
        num_filtered=num_filtered,
    )
