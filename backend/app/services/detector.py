"""
BroccoliDetector: loads the YOLOv8n model and runs detections.

This class wraps the Ultralytics YOLO model. We keep all
model-related code in one place so the rest of the app
does not need to know about Ultralytics.
"""

import hashlib
import logging
import secrets
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

# We import YOLO from ultralytics. This is the same library
# we used in Deliverable B for training.
from ultralytics import YOLO

from app import config

logger = logging.getLogger(__name__)


class BroccoliDetector:
    """Wrapper around the YOLOv8n model trained in Deliverable B."""

    # Read the weights file in 1 MB chunks when hashing so we never buffer
    # the whole (multi-MB) file in memory just to verify it.
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
            conf_threshold: Minimum confidence to keep a detection. This is
                only a fallback default; the /api/detect route always passes
                an explicit value, so it is not used in the live path.
            expected_sha256: Known-good SHA-256 of the weights file. When
                provided (or set via the EXPECTED_WEIGHTS_SHA256 env var),
                the file is hashed and compared BEFORE it is handed to
                Ultralytics/torch.load. A .pt file is a pickle archive, so
                torch.load executes any code embedded in it; verifying the
                hash first means a tampered file is rejected and never
                unpickled. When None/unset, verification is skipped (a
                warning is printed) and the file loads as before.
        """
        self.weights_path = Path(weights_path)
        self.conf_threshold = conf_threshold
        self.expected_sha256 = expected_sha256 or config.EXPECTED_WEIGHTS_SHA256

        # The Ultralytics YOLO model is NOT thread-safe: its internal
        # predictor reuses buffers/state between calls, and the Results
        # objects it returns reference that shared state. One detector
        # instance is shared across all requests (see main.py), and
        # inference now runs on a worker thread (run_in_threadpool in
        # detect.py), so two requests could otherwise call model.predict
        # at the same time. This lock serialises access so only one call
        # touches the model at a time.
        self._lock = threading.Lock()

        # If the weights file is missing, we still want the app
        # to start so the team can develop the frontend without it.
        # In that case self.model stays None: is_ready() reports False,
        # the /detect route returns 503, and predict() raises if called.
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
        """Check the weights file hash against the expected value.

        - No expected hash configured: behaviour depends on the environment.
          In production (DEPLOY_ENV=production) this is a fatal misconfig and
          raises, so a prod server never loads weights unverified ("fail
          closed"). In dev it logs a warning and skips the check, keeping the
          local flow working without extra configuration.
        - Expected hash configured and matches: return quietly; the caller
          proceeds to load the model.
        - Expected hash configured and does NOT match: raise RuntimeError so
          the tampered file is never unpickled. This is a security/tamper
          event and is intentionally NOT bypassable by ALLOW_MISSING_WEIGHTS
          (that flag only covers a genuinely missing file for frontend dev).

        Raises:
            RuntimeError: If running in production with no expected hash
                configured, or if an expected hash is set and the file's hash
                does not match it.
        """
        if not self.expected_sha256:
            # The hash check is what lets us reject a tampered checkpoint
            # before torch.load unpickles (and therefore executes) it. Silently
            # skipping it in production would be "fail-open", so we refuse to
            # start there; local dev stays optional (warn and continue).
            if config.IS_PROD:
                raise RuntimeError(
                    "EXPECTED_WEIGHTS_SHA256 is not set but DEPLOY_ENV=production. "
                    "Refusing to load weights unverified in production; set "
                    "EXPECTED_WEIGHTS_SHA256 to the known-good SHA-256 of best.pt "
                    "(or run with DEPLOY_ENV=dev for local development)."
                )
            logger.warning(
                "Weights integrity verification is DISABLED "
                "(EXPECTED_WEIGHTS_SHA256 not set). Set it to the known-good "
                "SHA-256 of best.pt to reject tampered weights before load."
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
        """Whether the detector can actually run inference.

        True only when the YOLO weights loaded successfully. When the
        weights file was missing at startup, self.model is None and this
        returns False. Both /api/health and /api/detect call this so the
        two readiness checks can never drift apart.
        """
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
            RuntimeError: If the model is not loaded (weights were missing
                at startup). Callers should check is_ready() first; the
                /detect route does this and returns 503 instead.
        """
        # If the model could not load, refuse loudly instead of silently
        # returning zero detections (which looks identical to a real photo
        # with no broccoli). This check is ABOVE the lock on purpose: it
        # touches no shared predictor state, so it needs no lock and never
        # acquires one. The /detect route guards with is_ready() and
        # returns 503 before getting here; this raise is a backstop for
        # any other caller that forgets to check.
        if self.model is None:
            raise RuntimeError(
                "Model is not loaded; cannot run prediction. "
                "Check that weights/best.pt exists."
            )

        # Pick which threshold to use this call.
        conf = (
            conf_threshold
            if conf_threshold is not None
            else self.conf_threshold
        )

        # Convert the PIL image to a NumPy array. YOLO accepts
        # both PIL and NumPy, but NumPy is a bit faster.
        img_array = np.array(image)

        # The shared YOLO model is not thread-safe, and the Results it
        # returns alias predictor state that the next predict() call
        # overwrites. So we hold the lock for the whole block below -
        # the predict() call AND the loop that reads results[0].boxes -
        # releasing it only once every box has been turned into plain
        # Python floats via .cpu().numpy().
        with self._lock:
            # Measure how long inference takes (for the demo UI). The
            # timer starts after the lock is held, so this reports pure
            # model time and excludes any time spent waiting for another
            # request's inference to finish.
            start_time = time.time()

            # Run the model. We pass conf to filter out low-confidence
            # boxes and verbose=False to keep the terminal clean.
            results = self.model.predict(
                source=img_array,
                conf=conf,
                verbose=False,
            )

            inference_time_ms = (time.time() - start_time) * 1000

            # Extract bounding boxes from the YOLO result object.
            detections = []
            if len(results) > 0:
                result = results[0]
                boxes = result.boxes

                # Loop over each detected box.
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

        # Lock released: `detections` now holds only plain Python floats,
        # safe to use while another request runs inference.
        return detections, inference_time_ms
