"""The /api/metadata endpoint: a model card for the running deployment.

Answers "which code and which model is this instance actually running,
and under which limits?" without needing shell access - the lifecycle
information (model version, weights hash, dataset lineage) comes from the
model registry resolved at startup, so the UI, monitoring, and operators
all read the same source of truth.

Lives outside the /detect router on purpose: like /health it is unauthenticated
and unthrottled, because it exposes no user data and integrations need it
before they hold an API key.
"""

from fastapi import APIRouter, Request

from app import config
from app.models.schemas import (
    AppInfo,
    InferenceConfig,
    MetadataResponse,
    ModelEvalMetrics,
    ModelInfo,
    UploadLimits,
)
from app.services.uploader import ImageUploader

router = APIRouter()


@router.get("/metadata", response_model=MetadataResponse)
def metadata(request: Request) -> MetadataResponse:
    """Describe the running app, the loaded model, and the API's limits."""
    detector = getattr(request.app.state, "detector", None)
    loaded = detector is not None and detector.is_ready()

    # Populated by the lifespan from the model registry; getattr keeps the
    # endpoint alive even if startup never ran (e.g. odd test harnesses).
    meta = getattr(request.app.state, "model_meta", {}) or {}
    entry = meta.get("registry_entry") or {}
    eval_metrics = entry.get("metrics") or {}

    return MetadataResponse(
        app=AppInfo(
            name="BroccoliDetect",
            version=config.APP_VERSION,
            git_sha=config.GIT_SHA,
            deploy_env=config.DEPLOY_ENV,
        ),
        model=ModelInfo(
            version=meta.get("version", config.MODEL_VERSION),
            loaded=loaded,
            source=meta.get("source", "missing"),
            verified=bool(meta.get("verified", False)),
            architecture=entry.get("architecture"),
            parameters=entry.get("parameters"),
            weights_file=meta.get("weights_file"),
            weights_sha256=meta.get("weights_sha256"),
            dataset_version=entry.get("dataset_version"),
            metrics=ModelEvalMetrics(
                map50=eval_metrics.get("map50"),
                mean_iou=eval_metrics.get("mean_iou"),
                test_set_size=eval_metrics.get("test_set_size"),
            ),
            notes=entry.get("notes"),
        ),
        inference=InferenceConfig(
            default_conf_threshold=config.DEFAULT_CONF,
            conf_min=config.CONF_MIN,
            conf_max=config.CONF_MAX,
            aspect_max_ratio=config.ASPECT_MAX_RATIO,
            fov_horizontal_deg=config.FOV_HORIZONTAL_DEG,
            default_camera_height_mm=config.DEFAULT_CAMERA_HEIGHT_MM,
            camera_height_min_mm=config.CAMERA_HEIGHT_MIN_MM,
            camera_height_max_mm=config.CAMERA_HEIGHT_MAX_MM,
            size_small_max_mm=config.SIZE_SMALL_MAX_MM,
            size_medium_max_mm=config.SIZE_MEDIUM_MAX_MM,
        ),
        limits=UploadLimits(
            max_file_mb=config.MAX_FILE_SIZE_BYTES // (1024 * 1024),
            max_request_mb=config.MAX_REQUEST_BODY_BYTES // (1024 * 1024),
            max_image_pixels=config.MAX_IMAGE_PIXELS,
            allowed_formats=sorted(ImageUploader.FORMAT_TO_EXT),
            rate_limit_max=config.RATE_LIMIT_MAX,
            rate_limit_window_seconds=config.RATE_LIMIT_WINDOW_SECONDS,
        ),
    )
