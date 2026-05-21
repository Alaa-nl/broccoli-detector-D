"""
The main /api/detect endpoint.

This route ties together all the services:
  1. ImageUploader  - saves the file
  2. BroccoliDetector - finds the crowns
  3. SizeEstimator - converts pixels to mm
  4. Annotator - draws boxes on the result image
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.models.schemas import (
    BoundingBox,
    CrownDetection,
    DetectionResponse,
)
from app.services.annotator import draw_detections
from app.services.size_estimator import SizeEstimator
from app.services.uploader import ImageUploader


router = APIRouter()

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
    detector = request.app.state.detector
    if detector is None:
        raise HTTPException(
            status_code=500,
            detail="Detector is not loaded on the server.",
        )

    raw_detections, inference_time_ms = detector.predict(
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
    draw_detections(pil_image, crowns_for_annotator, annotated_path)

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
