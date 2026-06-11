"""Model validation tests: the real YOLO weights, end to end.

Everything here is marked `model` so a weights-less environment can
deselect with `-m "not model"`. A synthetic image keeps the suite
self-contained; the contract is about output structure, not crown counts
(a blank frame legitimately yields zero detections).
"""

import io

import pytest
from PIL import Image

from app import config
from app.services.detector import BroccoliDetector

pytestmark = pytest.mark.model


def _synthetic_field(size=(640, 480)):
    """A green frame with a few darker blobs, vaguely field-like."""
    image = Image.new("RGB", size, (110, 140, 80))
    for cx, cy in ((160, 120), (400, 300), (520, 150)):
        for dx in range(-40, 41):
            for dy in range(-40, 41):
                if dx * dx + dy * dy <= 1600:
                    image.putpixel((cx + dx, cy + dy), (30, 90, 40))
    return image


def test_real_detector_prediction_contract(client):
    detector = client.app.state.detector
    assert detector.is_ready()

    detections, inference_time_ms = detector.predict(
        _synthetic_field(), conf_threshold=0.25
    )

    assert isinstance(detections, list)
    assert isinstance(inference_time_ms, float)
    assert inference_time_ms > 0

    # Whatever the model found must be geometrically and probabilistically
    # sane; the count itself is not asserted (synthetic input).
    for det in detections:
        assert set(det) == {"x1", "y1", "x2", "y2", "confidence"}
        assert det["x1"] < det["x2"]
        assert det["y1"] < det["y2"]
        assert 0.0 <= det["confidence"] <= 1.0


def test_detect_end_to_end_response_contract(client):
    buffer = io.BytesIO()
    _synthetic_field().save(buffer, format="JPEG")

    response = client.post(
        "/api/detect",
        files={"file": ("field.jpg", buffer.getvalue(), "image/jpeg")},
        data={"conf_threshold": "0.4", "camera_height_mm": "1000"},
    )

    assert response.status_code == 200
    body = response.json()

    # Full DetectionResponse contract.
    assert set(body) == {
        "image_id",
        "image_url",
        "annotated_url",
        "image_width",
        "image_height",
        "crowns",
        "num_crowns",
        "inference_time_ms",
        "camera_height_mm",
        "conf_threshold",
        "aspect_ratio_filter",
        "num_filtered",
    }
    assert isinstance(body["crowns"], list)
    assert body["num_crowns"] == len(body["crowns"])
    assert body["image_width"] == 640
    assert body["image_height"] == 480
    assert body["inference_time_ms"] > 0
    assert body["camera_height_mm"] == 1000.0
    assert body["conf_threshold"] == 0.4
    assert body["aspect_ratio_filter"] is True
    assert body["num_filtered"] >= 0

    assert body["image_url"].startswith("/uploads/")
    assert body["annotated_url"].startswith("/uploads/")
    # The annotated copy really exists on disk for /uploads to serve.
    annotated = config.UPLOAD_DIR / f"{body['image_id']}_annotated.jpg"
    assert annotated.exists()

    for crown in body["crowns"]:
        assert crown["bbox"]["x1"] < crown["bbox"]["x2"]
        assert crown["bbox"]["y1"] < crown["bbox"]["y2"]
        assert 0.0 <= crown["confidence"] <= 1.0
        assert crown["size_category"] in {"small", "medium", "large"}
        assert crown["diameter_mm"] == pytest.approx(
            crown["diameter_cm"] * 10.0
        )


def test_detector_rejects_wrong_weights_hash():
    # A deliberately wrong pin must stop the file from ever reaching
    # torch.load (.pt files are pickles; loading executes embedded code).
    with pytest.raises(RuntimeError, match="integrity"):
        BroccoliDetector(
            weights_path=str(config.WEIGHTS_PATH),
            expected_sha256="0" * 64,
        )


def test_detector_fails_closed_in_production_without_hash(monkeypatch):
    # Production with no expected hash is a fatal misconfig, not a warning.
    monkeypatch.setattr(config, "IS_PROD", True)
    monkeypatch.setattr(config, "EXPECTED_WEIGHTS_SHA256", None)
    with pytest.raises(RuntimeError, match="EXPECTED_WEIGHTS_SHA256"):
        BroccoliDetector(
            weights_path=str(config.WEIGHTS_PATH),
            expected_sha256=None,
        )
