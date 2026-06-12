"""Unit tests for the pinhole-model size estimator."""

import pytest

from app.services.size_estimator import SizeEstimator

# Hand-checked: ground width = 2 * height * tan(FOV/2).
# 2 * 1000 mm * tan(69.4deg / 2) = 2000 * tan(34.7deg) ~= 1384.87 mm.
EXPECTED_GROUND_WIDTH_MM = 1384.87


def test_mm_per_pixel_matches_hand_computed_ground_width():
    est = SizeEstimator(camera_height_mm=1000.0)
    # mm/px * image width recovers the visible ground width.
    for image_width_px in (640, 1280):
        ground_width = est.mm_per_pixel(image_width_px) * image_width_px
        assert ground_width == pytest.approx(EXPECTED_GROUND_WIDTH_MM, rel=1e-3)


def test_mm_per_pixel_linear_in_camera_height():
    # The pinhole model is linear in height: double the height, double the
    # ground width each pixel covers.
    low = SizeEstimator(camera_height_mm=1000.0).mm_per_pixel(640)
    high = SizeEstimator(camera_height_mm=2000.0).mm_per_pixel(640)
    assert high == pytest.approx(2.0 * low, rel=1e-9)


@pytest.mark.parametrize("bad_width", [0, -640])
def test_mm_per_pixel_rejects_non_positive_width(bad_width):
    est = SizeEstimator()
    with pytest.raises(ValueError):
        est.mm_per_pixel(bad_width)


@pytest.mark.parametrize(
    ("diameter_mm", "expected_category"),
    [
        (79.99, "small"),    # just under the small/medium boundary
        (80.0, "medium"),    # boundary itself is medium (< is strict)
        (129.99, "medium"),  # just under the medium/large boundary
        (130.0, "large"),    # boundary itself is large
    ],
)
def test_estimate_diameter_category_boundaries(diameter_mm, expected_category):
    est = SizeEstimator()
    # Pin the scale to exactly 1.0 mm/px so diameter == avg box side with no
    # floating-point drift - the boundary comparisons stay exact.
    est.mm_per_pixel = lambda image_width_px: 1.0

    result_mm, result_cm, category = est.estimate_diameter(
        bbox_width_px=diameter_mm,
        bbox_height_px=diameter_mm,
        image_width_px=640,
    )

    assert result_mm == pytest.approx(diameter_mm)
    assert result_cm == pytest.approx(diameter_mm / 10.0)
    assert category == expected_category


def test_estimate_diameter_averages_box_sides():
    est = SizeEstimator()
    est.mm_per_pixel = lambda image_width_px: 1.0
    # A 100x60 box should be reported as its mean side, 80 mm.
    result_mm, _, _ = est.estimate_diameter(
        bbox_width_px=100.0, bbox_height_px=60.0, image_width_px=640
    )
    assert result_mm == pytest.approx(80.0)


def test_estimate_diameter_rejects_non_positive_width():
    est = SizeEstimator()
    with pytest.raises(ValueError):
        est.estimate_diameter(
            bbox_width_px=50.0, bbox_height_px=50.0, image_width_px=0
        )
