"""
Central configuration for the BroccoliDetect backend.

Single source of truth for paths, env-overridable runtime settings, and the
detection/upload tunables that were previously scattered across modules.

This module is a dependency-free leaf: it imports only the standard library
(no app imports), so any module can import it without a circular import, and
it performs NO side effects (no mkdir, no PIL mutation) - callers keep those
in their own modules. Env vars are read ONCE at import; values are not
hot-reloaded.

Structural constants (file-format maps, colours, the request-id regex) stay in
their own modules - they are code, not configuration.
"""

import os
from pathlib import Path

# --- Paths ---------------------------------------------------------------
# config.py lives in app/, so parent.parent is the backend/ root. This is the
# single source of truth for these paths (they used to be derived separately,
# and inconsistently, in main.py and api/detect.py).
_BACKEND_DIR = Path(__file__).parent.parent
WEIGHTS_PATH = _BACKEND_DIR / "weights" / "best.pt"
UPLOAD_DIR = _BACKEND_DIR / "uploads"

# --- Environment / API docs gating ---------------------------------------
DEPLOY_ENV = os.getenv("DEPLOY_ENV", "dev")
IS_PROD = DEPLOY_ENV.strip().lower() == "production"

# --- Logging -------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# --- CORS ----------------------------------------------------------------
# Comma-separated allowlist of browser origins; defaults cover local dev.
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://localhost:8080",
    ).split(",")
    if origin.strip()
]

# --- Uploads: retention + size limits ------------------------------------
UPLOAD_TTL_SECONDS = int(os.getenv("UPLOAD_TTL_SECONDS", "3600"))      # 60 min
UPLOAD_SWEEP_SECONDS = int(os.getenv("UPLOAD_SWEEP_SECONDS", "600"))   # 10 min
MAX_REQUEST_BODY_BYTES = 15 * 1024 * 1024   # 15 MB (whole request body)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024      # 10 MB (uploaded file)
MAX_IMAGE_PIXELS = 25_000_000               # ~25 MP (decompression-bomb cap)
READ_CHUNK_BYTES = 64 * 1024                # 64 KB streaming read chunk

# --- Weights integrity + startup -----------------------------------------
EXPECTED_WEIGHTS_SHA256 = os.getenv("EXPECTED_WEIGHTS_SHA256")  # None if unset
ALLOW_MISSING_WEIGHTS = os.getenv("ALLOW_MISSING_WEIGHTS", "").lower() in (
    "1", "true", "yes",
)

# --- Rate limiting (per client IP) ---------------------------------------
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# --- Detection tunables --------------------------------------------------
# One confidence default everywhere; the floor matches the frontend slider.
DEFAULT_CONF = 0.40            # detector + /api/detect form default
CONF_MIN = 0.10                # /api/detect form floor (ge); matches the slider
CONF_MAX = 0.95                # /api/detect form ceiling (le)
ASPECT_MAX_RATIO = 1.6         # leaf filter: drop boxes more elongated than this

# --- Size estimation -----------------------------------------------------
DEFAULT_CAMERA_HEIGHT_MM = 1000.0   # 1 metre
CAMERA_HEIGHT_MIN_MM = 100          # /api/detect form bound (gt)
CAMERA_HEIGHT_MAX_MM = 5000         # /api/detect form bound (lt)
FOV_HORIZONTAL_DEG = 69.4           # Intel RealSense D415 horizontal FOV
SIZE_SMALL_MAX_MM = 80.0            # < 8 cm = small
SIZE_MEDIUM_MAX_MM = 130.0          # 8-13 cm = medium; >= large
