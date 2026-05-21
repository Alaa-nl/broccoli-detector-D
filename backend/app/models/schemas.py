"""
Pydantic data models for the API.

These classes describe the shape of the data that the API
returns. FastAPI uses them to validate inputs, build the
JSON response, and create the auto-generated docs at /docs.
"""

from typing import List

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """A single bounding box around one broccoli crown.

    Coordinates are in pixels of the original image
    (top-left is (0, 0)).
    """

    x1: float = Field(..., description="Left edge of the box in pixels.")
    y1: float = Field(..., description="Top edge of the box in pixels.")
    x2: float = Field(..., description="Right edge of the box in pixels.")
    y2: float = Field(..., description="Bottom edge of the box in pixels.")


class CrownDetection(BaseModel):
    """One detected broccoli crown with its size estimate."""

    crown_id: int = Field(..., description="Index of the crown (1, 2, 3, ...).")
    bbox: BoundingBox = Field(..., description="Bounding box of the crown.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence between 0 and 1.",
    )
    diameter_mm: float = Field(
        ...,
        description="Estimated crown diameter in millimetres.",
    )
    diameter_cm: float = Field(
        ...,
        description="Estimated crown diameter in centimetres.",
    )
    size_category: str = Field(
        ...,
        description="Friendly size label: 'small', 'medium', or 'large'.",
    )


class DetectionResponse(BaseModel):
    """The full JSON response from the /api/detect endpoint."""

    image_id: str = Field(..., description="Unique ID of this detection.")
    image_url: str = Field(..., description="URL of the original uploaded image.")
    annotated_url: str = Field(
        ...,
        description="URL of the image with green boxes drawn on it.",
    )
    image_width: int = Field(..., description="Original image width in pixels.")
    image_height: int = Field(..., description="Original image height in pixels.")
    crowns: List[CrownDetection] = Field(..., description="All detected crowns.")
    num_crowns: int = Field(..., description="How many crowns were found.")
    inference_time_ms: float = Field(
        ...,
        description="How long the model took, in milliseconds.",
    )
    camera_height_mm: float = Field(
        ...,
        description="Camera height used for size estimation (in mm).",
    )
    conf_threshold: float = Field(
        ...,
        description="Minimum YOLO confidence used to keep a detection.",
    )
    aspect_ratio_filter: bool = Field(
        ...,
        description="Whether elongated boxes (probably leaves) were dropped.",
    )
    num_filtered: int = Field(
        ...,
        description="How many boxes the post-processing filters removed.",
    )
