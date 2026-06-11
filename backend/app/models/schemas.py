"""
Pydantic data models for the API.

These classes describe the shape of the data that the API
returns. FastAPI uses them to validate inputs, build the
JSON response, and create the auto-generated docs at /docs.
"""

from typing import List, Optional

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


class AppInfo(BaseModel):
    """Identity of the running deployment (code side)."""

    name: str = Field(..., description="Application name.")
    version: str = Field(..., description="Application version.")
    git_sha: Optional[str] = Field(
        None, description="Git commit the image was built from (set by CI)."
    )
    deploy_env: str = Field(..., description="Deployment environment label.")


class ModelEvalMetrics(BaseModel):
    """Evaluation metrics recorded in the model registry at release time."""

    map50: Optional[float] = Field(None, description="mAP@0.5 on the test set.")
    mean_iou: Optional[float] = Field(None, description="Mean IoU on the test set.")
    test_set_size: Optional[int] = Field(
        None, description="Number of held-out test images."
    )


class ModelInfo(BaseModel):
    """Identity and provenance of the loaded model (the 'model card')."""

    version: str = Field(..., description="Model version tag (e.g. v1.0.0).")
    loaded: bool = Field(..., description="Whether the model is in memory.")
    source: str = Field(
        ...,
        description="Where the weights came from: 'local', 'remote' or 'missing'.",
    )
    verified: bool = Field(
        ...,
        description="Whether the weights' SHA-256 was checked before loading.",
    )
    architecture: Optional[str] = Field(None, description="Model architecture.")
    parameters: Optional[str] = Field(None, description="Parameter count.")
    weights_file: Optional[str] = Field(None, description="Weights filename.")
    weights_sha256: Optional[str] = Field(
        None, description="SHA-256 of the loaded weights file."
    )
    dataset_version: Optional[str] = Field(
        None, description="Dataset version the model was trained on."
    )
    metrics: Optional[ModelEvalMetrics] = Field(
        None, description="Evaluation metrics from the registry."
    )
    notes: Optional[str] = Field(None, description="Registry release notes.")


class InferenceConfig(BaseModel):
    """Inference tunables a client may want to mirror (slider bounds etc.)."""

    default_conf_threshold: float
    conf_min: float
    conf_max: float
    aspect_max_ratio: float
    fov_horizontal_deg: float
    default_camera_height_mm: float
    camera_height_min_mm: float
    camera_height_max_mm: float
    size_small_max_mm: float
    size_medium_max_mm: float


class UploadLimits(BaseModel):
    """Upload and throttling limits enforced by the API."""

    max_file_mb: int
    max_request_mb: int
    max_image_pixels: int
    allowed_formats: List[str]
    rate_limit_max: int
    rate_limit_window_seconds: float


class MetadataResponse(BaseModel):
    """The full JSON response from the /api/metadata endpoint."""

    app: AppInfo
    model: ModelInfo
    inference: InferenceConfig
    limits: UploadLimits
