"""Shared fixtures for the backend test suite.

The TestClient fixture is session-scoped on purpose: entering the context
manager runs the lifespan, which loads the real YOLO weights. One load
(~seconds on CPU) amortised across the whole suite keeps the run fast while
still exercising the genuine startup path (model_store resolution, model
card population, retention sweep task).
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import detect
from app.main import app
from app.services.rate_limiter import RateLimiter


@pytest.fixture(scope="session")
def client():
    """One app instance with the real model loaded, shared by all tests."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """Swap the module-global limiter for a roomy one, per test.

    The production limiter allows 10 requests / 60 s. The suite makes far
    more detect calls than that, so without this every test after the tenth
    would flake with a 429. The dedicated rate-limit test installs its own
    tight limiter on top; teardown here restores the real one either way.
    """
    original = detect._rate_limiter
    detect._rate_limiter = RateLimiter(10_000, 60)
    yield
    detect._rate_limiter = original


@pytest.fixture
def image_bytes():
    """Factory for tiny in-memory test images.

    Small dimensions keep encode + inference time negligible; the format
    parameter lets tests produce real JPEG or PNG bytes (the uploader
    validates by decoded content, not filename).
    """

    def _make(fmt="JPEG", size=(64, 48), color=(34, 120, 60)):
        buffer = io.BytesIO()
        Image.new("RGB", size, color).save(buffer, format=fmt)
        return buffer.getvalue()

    return _make


class NotReadyDetector:
    """Stands in for a detector whose weights never loaded."""

    def is_ready(self):
        return False

    def predict(self, *args, **kwargs):  # pragma: no cover - guard only
        raise RuntimeError("Model is not loaded.")


@pytest.fixture
def not_ready_detector(client):
    """Make the app behave as if weights failed to load, then restore.

    Restoring matters because the client (and its real detector) is shared
    across the whole session.
    """
    original = client.app.state.detector
    client.app.state.detector = NotReadyDetector()
    yield
    client.app.state.detector = original
