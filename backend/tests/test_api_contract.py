"""API contract tests: status codes, response shapes and headers.

These run against the session-wide TestClient, so the real model is loaded
and the full middleware stack (request id, metrics, body size limit) is in
the loop.
"""

import re

import pytest

from app.api import detect
from app.services.rate_limiter import RateLimiter

REGISTRY_SHA = "bf5f8500bba6a3b52bb55aec0212eef64581bff199e0e64a9f42322bf04acf6f"


# --- Health and readiness ---------------------------------------------------


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True}


def test_health_degraded_without_model(client, not_ready_detector):
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "model_loaded": False}


def test_ready_reports_all_checks(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"model_loaded": True, "uploads_writable": True}


# --- Metadata (model card) --------------------------------------------------


def test_metadata_describes_app_and_model(client):
    response = client.get("/api/metadata")
    assert response.status_code == 200
    body = response.json()

    assert body["app"]["name"] == "BroccoliDetect"

    model = body["model"]
    assert model["version"] == "v1.0.0"
    assert model["loaded"] is True
    assert model["source"] == "local"
    # The hash of the file on disk must match the registry's released hash.
    assert model["weights_sha256"] == REGISTRY_SHA
    assert model["metrics"]["map50"] == 0.976

    assert body["limits"]["allowed_formats"] == ["JPEG", "PNG"]


# --- Prometheus -------------------------------------------------------------


def test_metrics_endpoint_exposes_app_series(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "broccoli_http_requests_total" in response.text
    assert "broccoli_app_info" in response.text


# --- Request id header ------------------------------------------------------


def test_request_id_present_on_every_response(client):
    response = client.get("/api/health")
    assert "x-request-id" in response.headers


def test_request_id_echoes_well_formed_inbound_value(client):
    response = client.get(
        "/api/health", headers={"X-Request-ID": "trace-abc.123"}
    )
    assert response.headers["x-request-id"] == "trace-abc.123"


def test_request_id_replaces_malformed_inbound_value(client):
    # "!!!" fails the allowlist regex, so a fresh id must be generated
    # instead of reflecting attacker-controlled bytes into a header.
    response = client.get("/api/health", headers={"X-Request-ID": "!!!"})
    returned = response.headers["x-request-id"]
    assert returned != "!!!"
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,64}", returned)


# --- /api/detect input validation -------------------------------------------


def test_detect_missing_file_is_422(client):
    response = client.post("/api/detect")
    assert response.status_code == 422


@pytest.mark.parametrize("conf", ["0.05", "0.96"])
def test_detect_conf_threshold_out_of_bounds_is_422(client, image_bytes, conf):
    response = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
        data={"conf_threshold": conf},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("height", ["99", "5001"])
def test_detect_camera_height_out_of_bounds_is_422(client, image_bytes, height):
    response = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
        data={"camera_height_mm": height},
    )
    assert response.status_code == 422


def test_detect_rejects_txt_upload(client):
    response = client.post(
        "/api/detect",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 400


def test_detect_rejects_garbage_bytes_named_jpg(client):
    response = client.post(
        "/api/detect",
        files={"file": ("fake.jpg", b"these are not pixels", "image/jpeg")},
    )
    assert response.status_code == 400


def test_detect_oversized_body_is_413(client):
    # One byte over the 15 MB request cap. The middleware trusts
    # Content-Length, so this is rejected before the body is parsed.
    oversized = b"x" * (15 * 1024 * 1024 + 1)
    response = client.post(
        "/api/detect",
        content=oversized,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413


def test_detect_without_model_is_503(client, image_bytes, not_ready_detector):
    response = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 503


# --- Authentication ----------------------------------------------------------


def test_detect_auth_enforced_when_api_key_set(client, image_bytes, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret")

    no_header = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
    )
    assert no_header.status_code == 401

    wrong_key = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
        headers={"X-API-Key": "wrong"},
    )
    assert wrong_key.status_code == 401

    correct_key = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
        headers={"X-API-Key": "test-secret"},
    )
    assert correct_key.status_code == 200


# --- Rate limiting ------------------------------------------------------------


def test_detect_rate_limit_returns_429_with_retry_after(client, image_bytes):
    # Tight limiter just for this test; the autouse fixture restores the
    # production limiter afterwards regardless.
    detect._rate_limiter = RateLimiter(1, 60)

    first = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/detect",
        files={"file": ("img.jpg", image_bytes(), "image/jpeg")},
    )
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
