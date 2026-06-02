"""Health and readiness endpoints, useful for monitoring."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/health")
def health(request: Request, response: Response):
    """Liveness + model check (cheap; used by the platform healthcheck).

    Same body shape as before, but now signals degraded state with HTTP 503
    when the model is not loaded, so load balancers / the platform react
    instead of seeing a misleading 200. Kept lightweight (no inference, no
    disk I/O) so it stays well within the healthcheck timeout.
    """
    # We use the same is_ready() check that /detect guards on, so the two
    # can never drift. getattr handles the (unlikely) case where the
    # detector was never set on app.state.
    detector = getattr(request.app.state, "detector", None)
    model_loaded = detector is not None and detector.is_ready()

    if not model_loaded:
        response.status_code = 503
        return {"status": "degraded", "model_loaded": False}
    return {"status": "ok", "model_loaded": True}


@router.get("/ready")
def ready(request: Request, response: Response):
    """Readiness probe: confirms the server can actually serve a detection.

    Deeper than /health: besides the model being loaded, it verifies the
    uploads directory is writable by writing and deleting a tiny probe file
    (a real /detect must save the original and annotated images there). This
    is an on-demand readiness check and is intentionally NOT the platform
    healthcheck path, so /health stays cheap. Returns 503 (with which check
    failed) when not ready.
    """
    detector = getattr(request.app.state, "detector", None)
    model_loaded = detector is not None and detector.is_ready()

    # Confirm the uploads dir is writable: a read-only or full disk would make
    # every /detect fail at save time. The probe name starts with "." so the
    # retention sweep ignores it; we delete it immediately regardless.
    uploads_writable = False
    upload_dir = getattr(request.app.state, "upload_dir", None)
    if upload_dir is not None:
        probe = Path(upload_dir) / f".readycheck_{uuid.uuid4().hex}"
        try:
            probe.write_bytes(b"ok")
            uploads_writable = True
        except OSError:
            uploads_writable = False
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    ready_ok = model_loaded and uploads_writable
    if not ready_ok:
        response.status_code = 503
    return {
        "status": "ready" if ready_ok else "not_ready",
        "checks": {
            "model_loaded": model_loaded,
            "uploads_writable": uploads_writable,
        },
    }
