"""
The main /api/detect endpoint.

This route ties together all the services:
  1. ImageUploader  - saves the file
  2. BroccoliDetector - finds the crowns
  3. SizeEstimator - converts pixels to mm
  4. Annotator - draws boxes on the result image
"""

import os
import random
import secrets
from pathlib import Path
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

from app.models.schemas import (
    BoundingBox,
    CrownDetection,
    DetectionResponse,
)
from app.services.annotator import draw_detections
from app.services.rate_limiter import RateLimiter
from app.services.size_estimator import SizeEstimator
from app.services.uploader import ImageUploader


# --- Access control for the public upload endpoint (P0-4) ---------------
#
# The backend is internet-facing, so we (1) optionally require an API key
# and (2) rate-limit per client. Auth is OPT-IN: it is enforced only when
# the API_KEY env var is set. Local dev (no API_KEY) stays keyless; in
# production Render sets API_KEY on the backend and the nginx frontend
# injects the same value as the X-API-Key header (the browser never sees
# it).

# Rate-limit configuration (per client IP). Defaults to 10 requests/min.
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
_rate_limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SECONDS)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Reject the request unless it carries the configured API key.

    No-op when API_KEY is unset (development), so the keyless local flow
    keeps working. Uses a constant-time compare to avoid leaking the key
    via timing.
    """
    expected = os.getenv("API_KEY")
    if not expected:
        return  # Auth disabled (no key configured).
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )


def _client_key(request: Request) -> str:
    """Best-effort client identity for rate limiting.

    Behind nginx the real client IP arrives in X-Forwarded-For /
    X-Real-IP (set by the proxy); fall back to the socket peer otherwise.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
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
    # Occasionally drop stale keys so the limiter's memory stays bounded.
    if random.random() < 0.01:
        _rate_limiter._prune()


# Both guards run on every route in this router. /api/health lives in a
# separate router, so monitoring stays open and unthrottled.
router = APIRouter(dependencies=[Depends(require_api_key), Depends(rate_limit)])

# Folder where uploads and annotated images are stored.
# This must match the path used in main.py.
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"


@router.post("/detect", response_model=DetectionResponse)
async def detect_broccoli(
    request: Request,
    file: UploadFile = File(..., description="A JPG or PNG broccoli image."),
    camera_height_mm: float = Form(
        default=1000.0,
        description="Camera height above the ground in mm "
                    "(default 1000 mm = 1 metre).",
    ),
    conf_threshold: float = Form(
        default=0.40,
        ge=0.05,
        le=0.95,
        description="Minimum confidence (0-1). Higher = fewer false "
                    "positives but also fewer detections. Default 0.4.",
    ),
    aspect_ratio_filter: bool = Form(
        default=True,
        description="If True, drop boxes that are too elongated "
                    "(probably leaves, not crowns).",
    ),
):
    """Run broccoli crown detection on an uploaded image.

    Steps:
      1. Save the file to disk (with validation).
      2. Run YOLOv8n to find the bounding boxes.
      3. Optionally drop too-elongated boxes (leaf filter).
      4. Convert each box to a crown diameter in mm.
      5. Draw the boxes on a new annotated image.
      6. Return a JSON response with all the results.
    """
    # --- Step 1: save the upload ---
    uploader = ImageUploader(upload_dir=UPLOAD_DIR)
    saved_path, image_id, pil_image = await uploader.save(file)

    img_width = pil_image.width
    img_height = pil_image.height

    # --- Step 2: run the YOLO model with the chosen confidence ---
    # The detector was loaded one time in main.py and stored on app.state.
    # The detector object always exists (main.py sets it at startup), but
    # its model is None when best.pt was missing. Guard on is_ready() so a
    # misconfigured server returns a clear 503 (service not ready) instead
    # of silently returning zero crowns at HTTP 200.
    detector = request.app.state.detector
    if detector is None or not detector.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Detection model is not loaded on the server.",
        )

    # Run YOLO inference on a worker thread so it does not block the
    # event loop. The call is CPU-bound and can take hundreds of ms;
    # offloading it keeps the server responsive (health checks, other
    # uploads) while one detection is running. The detector serialises
    # access to the shared model internally with a lock.
    raw_detections, inference_time_ms = await run_in_threadpool(
        detector.predict,
        pil_image,
        conf_threshold=conf_threshold,
    )
    detections_before_filter = len(raw_detections)

    # --- Step 3: optional aspect-ratio filter ---
    # Real broccoli crowns are roughly square when seen from above.
    # Boxes that are much wider than tall (or much taller than wide)
    # are usually leaves, not crowns. We drop them when enabled.
    if aspect_ratio_filter:
        max_ratio = 1.6  # Allow some tolerance
        kept = []
        for det in raw_detections:
            w = det["x2"] - det["x1"]
            h = det["y2"] - det["y1"]
            if w > 0 and h > 0:
                ratio = max(w, h) / min(w, h)
                if ratio <= max_ratio:
                    kept.append(det)
        raw_detections = kept

    num_filtered = detections_before_filter - len(raw_detections)

    # --- Step 4: convert each box into a CrownDetection ---
    size_estimator = SizeEstimator(camera_height_mm=camera_height_mm)
    crowns_for_annotator = []
    crown_models = []

    for i, det in enumerate(raw_detections, start=1):
        bbox_w_px = det["x2"] - det["x1"]
        bbox_h_px = det["y2"] - det["y1"]

        diameter_mm, diameter_cm, category = size_estimator.estimate_diameter(
            bbox_width_px=bbox_w_px,
            bbox_height_px=bbox_h_px,
            image_width_px=img_width,
        )

        crown_dict = {
            "crown_id": i,
            "bbox": {
                "x1": det["x1"], "y1": det["y1"],
                "x2": det["x2"], "y2": det["y2"],
            },
            "confidence": det["confidence"],
            "diameter_mm": diameter_mm,
            "diameter_cm": diameter_cm,
            "size_category": category,
        }
        crowns_for_annotator.append(crown_dict)

        # Also build the Pydantic model for the response.
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
    annotated_path = UPLOAD_DIR / annotated_filename
    # Drawing the boxes and JPEG-encoding the result (annotated.save)
    # is also blocking, so offload it to a worker thread too.
    await run_in_threadpool(
        draw_detections,
        pil_image,
        crowns_for_annotator,
        annotated_path,
    )

    # --- Step 6: build the response ---
    # The frontend will call these URLs to show the images.
    image_url = f"/uploads/{saved_path.name}"
    annotated_url = f"/uploads/{annotated_filename}"

    return DetectionResponse(
        image_id=image_id,
        image_url=image_url,
        annotated_url=annotated_url,
        image_width=img_width,
        image_height=img_height,
        crowns=crown_models,
        num_crowns=len(crown_models),
        inference_time_ms=inference_time_ms,
        camera_height_mm=camera_height_mm,
        conf_threshold=conf_threshold,
        aspect_ratio_filter=aspect_ratio_filter,
        num_filtered=num_filtered,
    )
