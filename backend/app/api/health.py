"""Simple health-check endpoint, useful for monitoring."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
def health(request: Request):
    """Return a small JSON object that says the server is up."""
    # Check whether the model is loaded (so we know if detections will work).
    model_loaded = getattr(request.app.state, "detector", None) is not None
    if model_loaded:
        model_loaded = request.app.state.detector.model is not None

    return {
        "status": "ok",
        "model_loaded": model_loaded,
    }
