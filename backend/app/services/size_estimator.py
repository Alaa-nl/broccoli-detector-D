"""Estimates crown size in mm from bounding box pixel dimensions.

Uses a pinhole camera model with a configurable camera height (the JPG
dataset has no per-pixel depth, so height is a fixed assumption).
See docs/size-estimation.md for the math and known limits.
"""

import math
from typing import Tuple

from app import config


class SizeEstimator:
    """Convert bounding box pixel size to crown diameter in mm."""

    # From config (Intel D415 horizontal FOV in degrees).
    DEFAULT_FOV_HORIZONTAL_DEG = config.FOV_HORIZONTAL_DEG

    # From config (1000 mm = hip height for a walking operator).
    DEFAULT_CAMERA_HEIGHT_MM = config.DEFAULT_CAMERA_HEIGHT_MM

    # Size category thresholds (from config).
    SMALL_MAX_MM = config.SIZE_SMALL_MAX_MM    
    MEDIUM_MAX_MM = config.SIZE_MEDIUM_MAX_MM  

    def __init__(
        self,
        camera_height_mm: float = DEFAULT_CAMERA_HEIGHT_MM,
        fov_horizontal_deg: float = DEFAULT_FOV_HORIZONTAL_DEG,
    ):
        """Set up the estimator with camera parameters.

        Args:
            camera_height_mm: Height of camera above the ground (mm).
            fov_horizontal_deg: Horizontal field of view (degrees).
        """
        self.camera_height_mm = camera_height_mm
        self.fov_horizontal_deg = fov_horizontal_deg

    def mm_per_pixel(self, image_width_px: int) -> float:
        """Compute the scale factor for one specific image width.

        Args:
            image_width_px: Width of the input image in pixels.

        Returns:
            Number of millimetres that one pixel represents
            at the ground plane.

        Raises:
            ValueError: If image_width_px is not positive.
        """
        
        # Explicit guard so callers get ValueError instead of ZeroDivisionError.
        if image_width_px <= 0:
            raise ValueError("image_width_px must be positive.")

        fov_rad = math.radians(self.fov_horizontal_deg)

        # Width of the ground area the camera sees (in mm).
        ground_width_mm = 2.0 * self.camera_height_mm * math.tan(fov_rad / 2.0)

        return ground_width_mm / image_width_px

    def estimate_diameter(
        self,
        bbox_width_px: float,
        bbox_height_px: float,
        image_width_px: int,
    ) -> Tuple[float, float, str]:
        """Estimate the crown diameter from one bounding box.

        We use the average of the box width and height,
        because broccoli crowns are roughly circular when
        viewed from above.

        Args:
            bbox_width_px: Width of the bounding box (pixels).
            bbox_height_px: Height of the bounding box (pixels).
            image_width_px: Width of the full image (pixels).

        Returns:
            Tuple of (diameter_mm, diameter_cm, size_category).
        """
        scale = self.mm_per_pixel(image_width_px)

        avg_side_px = (bbox_width_px + bbox_height_px) / 2.0
        diameter_mm = avg_side_px * scale
        diameter_cm = diameter_mm / 10.0

        # Bucket into small / medium / large.
        if diameter_mm < self.SMALL_MAX_MM:
            category = "small"
        elif diameter_mm < self.MEDIUM_MAX_MM:
            category = "medium"
        else:
            category = "large"

        return diameter_mm, diameter_cm, category
