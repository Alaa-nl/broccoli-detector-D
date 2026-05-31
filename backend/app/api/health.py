"""Simple health-check endpoint, useful for monitoring."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    """Return a small JSON object that says the server is up."""
    # Check whether the model is loaded (so we know if detections will work).
    # We use the same is_ready() check that /detect guards on, so the two
    # can never drift. getattr handles the (unlikely) case where the
    # detector was never set on app.state.
    detector = getattr(request.app.state, "detector", None)
    model_loaded = detector is not None and detector.is_ready()

    return {
        "status": "ok",
        "model_loaded": model_loaded,
    }
