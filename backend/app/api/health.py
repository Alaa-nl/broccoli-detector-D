"""Health and readiness endpoints, useful for monitoring."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/health")
def health(request: Request, response: Response):
    """Liveness + model check, used by the platform healthcheck.

    Returns 503 when the model isn't loaded so load balancers see the
    degraded state. Kept cheap (no inference, no disk I/O) to stay within
    the healthcheck timeout, so don't add heavy checks here.
    """
    # getattr handles the (unlikely) case where startup didn't set the detector.
    detector = getattr(request.app.state, "detector", None)
    model_loaded = detector is not None and detector.is_ready()

    if not model_loaded:
        response.status_code = 503
        return {"status": "degraded", "model_loaded": False}
    return {"status": "ok", "model_loaded": True}


@router.get("/ready")
def ready(request: Request, response: Response):
    """Readiness probe: confirms the server can actually serve a detection.

    Goes beyond /health by also writing a probe file to the uploads
    directory, since /detect must save images there. On-demand only,
    not on the platform healthcheck path (so /health stays cheap).
    Returns 503 when any check fails.
    """
    detector = getattr(request.app.state, "detector", None)
    model_loaded = detector is not None and detector.is_ready()

    # Probe write to uploads/ so a read-only or full disk surfaces here
    # instead of failing every /detect. Dot prefix avoids the retention sweep.
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
