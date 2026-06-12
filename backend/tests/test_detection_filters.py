"""Unit tests for the aspect-ratio (leaf) filter."""

import copy

from app.services.detection_filters import filter_by_aspect_ratio


def _box(width, height, confidence=0.9):
    return {
        "x1": 10.0,
        "y1": 20.0,
        "x2": 10.0 + width,
        "y2": 20.0 + height,
        "confidence": confidence,
    }


def test_keeps_near_square_boxes():
    detections = [_box(100, 100), _box(100, 90), _box(80, 100)]
    assert filter_by_aspect_ratio(detections) == detections


def test_drops_elongated_boxes_both_orientations():
    # Ratio 2.0 in either orientation - typical leaf shapes.
    wide = _box(200, 100)
    tall = _box(100, 200)
    square = _box(100, 100)
    assert filter_by_aspect_ratio([wide, square, tall]) == [square]


def test_boundary_ratio_is_kept():
    # 160/100 is exactly the 1.6 default cap; the comparison is <=, so the
    # boundary box must survive.
    boundary = _box(160, 100)
    assert filter_by_aspect_ratio([boundary]) == [boundary]
    # Just over the cap is dropped.
    assert filter_by_aspect_ratio([_box(161, 100)]) == []


def test_drops_degenerate_boxes():
    zero_width = _box(0, 100)
    zero_height = _box(100, 0)
    negative = _box(-50, 100)  # x2 < x1
    assert filter_by_aspect_ratio([zero_width, zero_height, negative]) == []


def test_input_list_is_not_mutated():
    detections = [_box(100, 100), _box(300, 100)]
    snapshot = copy.deepcopy(detections)

    result = filter_by_aspect_ratio(detections)

    assert detections == snapshot
    # A new list comes back even when everything passes.
    assert result is not detections
