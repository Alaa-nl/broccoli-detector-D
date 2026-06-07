"""YOLOv8n inference wrapper with optional SHA-256 weights verification."""

import hashlib
import logging
import secrets
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image


from ultralytics import YOLO

from app import config

logger = logging.getLogger(__name__)


class BroccoliDetector:
    """Thread-safe YOLOv8n inference wrapper."""

    # Hash the .pt in 1 MB chunks to avoid loading it all into memory.
    _HASH_CHUNK_BYTES = 1024 * 1024

    def __init__(
        self,
        weights_path: str,
        conf_threshold: float = config.DEFAULT_CONF,
        expected_sha256: Optional[str] = None,
    ):
        """Load the model from a .pt file.

        Args:
            weights_path: Path to best.pt (the trained model file).
            conf_threshold: Default min confidence. Fallback only; the
                /api/detect route always passes an explicit value.
            expected_sha256: Known-good SHA-256 of the weights file (or
                set via EXPECTED_WEIGHTS_SHA256). Hashed and compared
                before torch.load runs, since .pt files are pickles and
                loading executes embedded code. None skips the check.
        """
        self.weights_path = Path(weights_path)
        self.conf_threshold = conf_threshold
        self.expected_sha256 = expected_sha256 or config.EXPECTED_WEIGHTS_SHA256

        # YOLO is not thread-safe: the predictor reuses buffers between calls
        # and Results alias that state. Inference runs on a worker thread, so
        # serialise access to the shared model.
        self._lock = threading.Lock()

        # Missing weights: keep self.model = None so frontend dev can
        # iterate without best.pt. is_ready() will report False and
        # /detect returns 503.
        if not self.weights_path.exists():
            logger.warning(
                "Weights file not found (%s). The detector will return empty "
                "results until best.pt is placed in the weights folder.",
                self.weights_path.name,
            )
            self.model = None
        else:
            # Verify the file's integrity BEFORE handing it to Ultralytics.
            # YOLO(...) calls torch.load, which unpickles the .pt archive and
            # executes any code embedded in it. Hashing the raw bytes first
            # means a swapped/tampered file is rejected without ever being
            # unpickled.
            self._verify_integrity()

            # Load the model into memory one time.
            self.model = YOLO(str(self.weights_path))

    def _verify_integrity(self) -> None:
        """Verify the weights file's SHA-256 against the expected value.

        In production, an unset expected hash is a fatal misconfig: we
        raise rather than load weights unverified (fail-closed). In dev,
        we log a warning and skip the check so local work isn't blocked.
        When a hash is configured, a mismatch raises so the tampered file
        is never unpickled.

        Raises:
            RuntimeError: In production with no expected hash, or when the
                hash does not match.
        """
        if not self.expected_sha256:
            if config.IS_PROD:
                raise RuntimeError(
                    "EXPECTED_WEIGHTS_SHA256 must be set when "
                    "DEPLOY_ENV=production. Refusing to load weights unverified."
                )
            logger.warning(
                "Weights integrity check skipped (EXPECTED_WEIGHTS_SHA256 not set)."
            )
            return

        actual = self._compute_sha256(self.weights_path)

        # Constant-time, case-insensitive comparison (hex digests may differ
        # in case). compare_digest needs equal-length inputs, so normalise.
        if not secrets.compare_digest(actual, self.expected_sha256.strip().lower()):
            # Do NOT include the computed/expected digests or the absolute
            # path in the message (avoid leaking internal state).
            raise RuntimeError(
                "Weights integrity check failed: best.pt does not match the "
                "expected SHA-256. Refusing to load a potentially tampered "
                "model file."
            )

    @classmethod
    def _compute_sha256(cls, path: Path) -> str:
        """Return the lowercase hex SHA-256 of a file, read in chunks."""
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(cls._HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    def is_ready(self) -> bool:
        """True if the model loaded successfully and inference is possible."""
        return self.model is not None

    def predict(
        self,
        image: Image.Image,
        conf_threshold: Optional[float] = None,
    ) -> Tuple[List[dict], float]:
        """Run detection on one image.

        Args:
            image: A PIL image (RGB) loaded from the user upload.
            conf_threshold: Optional override of the default conf
                threshold for this single call. When None, the
                value from the constructor is used.

        Returns:
            A tuple of (detections, inference_time_ms) where
            detections is a list of dicts with keys:
            'x1', 'y1', 'x2', 'y2', 'confidence'.

        Raises:
            RuntimeError: If the model is not loaded. Check is_ready() first.
        """
        
        # Backstop if a caller skipped is_ready().
        if self.model is None:
            raise RuntimeError(
                "Model is not loaded; cannot run prediction. "
                "Check that weights/best.pt exists."
            )

        conf = (
            conf_threshold
            if conf_threshold is not None
            else self.conf_threshold
        )

        # NumPy array is faster than PIL for YOLO input.
        img_array = np.array(image)

        # Hold the lock through both predict() and the box-extraction loop:
        # Results alias predictor state that the next call overwrites.
        with self._lock:
            # Timer inside the lock: measures pure inference, excludes wait.
            start_time = time.monotonic()

            # verbose=False keeps the terminal clean during inference.
            results = self.model.predict(
                source=img_array,
                conf=conf,
                verbose=False,
            )

            inference_time_ms = (time.monotonic() - start_time) * 1000

            detections = []
            if len(results) > 0:
                result = results[0]
                boxes = result.boxes

                for i in range(len(boxes)):
                    # xyxy gives us [x1, y1, x2, y2] in original image pixels.
                    xyxy = boxes.xyxy[i].cpu().numpy()
                    box_conf = float(boxes.conf[i].cpu().numpy())

                    detections.append({
                        "x1": float(xyxy[0]),
                        "y1": float(xyxy[1]),
                        "x2": float(xyxy[2]),
                        "y2": float(xyxy[3]),
                        "confidence": box_conf,
                    })

        # detections is plain floats here, safe to use after the lock releases.
        return detections, inference_time_ms
