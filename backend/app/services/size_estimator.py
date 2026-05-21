"""
SizeEstimator: converts bounding box pixel size to real-world size.

Background
----------
The original RGB-D dataset has depth data, but the JPGs we use
do not include per-pixel depth. So we use a simple pinhole camera
model to estimate crown diameter from the bounding box width.

The math
--------
The Intel RealSense D415 used to record the dataset has a
horizontal field of view of about 69.4 degrees (Intel docs).

If the camera is at height H above the ground and points
straight down, the width of the ground area it sees is:

    ground_width_mm = 2 * H * tan(FOV / 2)

We then get the scale factor (millimetres per pixel):

    mm_per_pixel = ground_width_mm / image_width_px

And finally the crown diameter:

    crown_diameter_mm = bbox_width_px * mm_per_pixel

Limits of this simple model
---------------------------
- It assumes the camera is at a fixed height. The team asked
  Surya about this by email but did not get a final answer.
  The default height (1000 mm) is a sensible guess based on
  a person walking the row with a hand-held camera.
- It ignores lens distortion near the image edges.
- It uses bounding box width as a proxy for crown diameter.

The user can change the camera height in the Settings screen
to calibrate the estimate against a known reference.
"""

import math
from typing import Tuple


class SizeEstimator:
    """Convert bounding box pixel size to crown diameter in mm."""

    # Horizontal field of view of the Intel RealSense D415, in degrees.
    # Source: Intel RealSense D415 datasheet (69.4 H x 42.5 V).
    DEFAULT_FOV_HORIZONTAL_DEG = 69.4

    # Default camera height above the ground in millimetres.
    # 1000 mm = 1 metre, which matches a person walking with
    # the camera held at hip / waist level.
    DEFAULT_CAMERA_HEIGHT_MM = 1000.0

    # Thresholds (in mm) for the friendly size labels.
    # Based on common retail size grades for broccoli crowns.
    SMALL_MAX_MM = 80.0   # < 8 cm = small / immature
    MEDIUM_MAX_MM = 130.0  # 8-13 cm = medium (good for retail)
    # >= 130 mm = large

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
        """
        # Convert FOV from degrees to radians for math.tan().
        fov_rad = math.radians(self.fov_horizontal_deg)

        # Width of the ground area the camera sees (in mm).
        ground_width_mm = 2.0 * self.camera_height_mm * math.tan(fov_rad / 2.0)

        # Scale factor: mm per pixel.
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
        # Get scale factor for this image size.
        scale = self.mm_per_pixel(image_width_px)

        # Average the two box sides, then convert to mm.
        avg_side_px = (bbox_width_px + bbox_height_px) / 2.0
        diameter_mm = avg_side_px * scale
        diameter_cm = diameter_mm / 10.0

        # Pick a friendly label so the farmer can decide quickly.
        if diameter_mm < self.SMALL_MAX_MM:
            category = "small"
        elif diameter_mm < self.MEDIUM_MAX_MM:
            category = "medium"
        else:
            category = "large"

        return diameter_mm, diameter_cm, category
