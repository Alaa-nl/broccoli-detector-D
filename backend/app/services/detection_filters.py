"""
Detection post-processing filters.

Pure functions that operate on the raw detection dicts the detector returns
(`{'x1','y1','x2','y2','confidence'}`). Keeping them here - out of the HTTP
route - makes them reusable and unit-testable in isolation, consistent with
the rest of the service layer.
"""

from typing import List

from app import config


def filter_by_aspect_ratio(
    detections: List[dict],
    max_ratio: float = config.ASPECT_MAX_RATIO,
) -> List[dict]:
    """Drop boxes that are too elongated to be a broccoli crown.

    Real crowns are roughly square when viewed from above; a box much wider
    than tall (or vice versa) is usually a leaf. A detection is kept only when
    its longer side is at most `max_ratio` times its shorter side. Degenerate
    boxes (zero or negative width/height) are also dropped.

    Args:
        detections: Raw detection dicts with 'x1','y1','x2','y2' in pixels.
        max_ratio: Maximum allowed longer/shorter side ratio (>= 1).

    Returns:
        A new list containing only the detections that pass. The input list is
        not modified.
    """
    kept = []
    for det in detections:
        w = det["x2"] - det["x1"]
        h = det["y2"] - det["y1"]
        # The w/h guards short-circuit before the division, so a degenerate
        # box is dropped without a ZeroDivisionError.
        if w > 0 and h > 0 and max(w, h) / min(w, h) <= max_ratio:
            kept.append(det)
    return kept
