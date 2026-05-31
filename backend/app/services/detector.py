"""
BroccoliDetector: loads the YOLOv8n model and runs detections.

This class wraps the Ultralytics YOLO model. We keep all
model-related code in one place so the rest of the app
does not need to know about Ultralytics.
"""

import threading
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

# We import YOLO from ultralytics. This is the same library
# we used in Deliverable B for training.
from ultralytics import YOLO


class BroccoliDetector:
    """Wrapper around the YOLOv8n model trained in Deliverable B."""

    def __init__(self, weights_path: str, conf_threshold: float = 0.25):
        """Load the model from a .pt file.

        Args:
            weights_path: Path to best.pt (the trained model file).
            conf_threshold: Minimum confidence to keep a detection.
                The default 0.25 is the standard value used by
                Ultralytics during evaluation.
        """
        self.weights_path = Path(weights_path)
        self.conf_threshold = conf_threshold

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
            print(
                f"WARNING: weights file not found at {self.weights_path}. "
                f"The detector will return empty results until you copy "
                f"best.pt into the backend/weights/ folder."
            )
            self.model = None
        else:
            # Load the model into memory one time.
            self.model = YOLO(str(self.weights_path))

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
        conf_threshold: float = None,
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
                    conf = float(boxes.conf[i].cpu().numpy())

                    detections.append({
                        "x1": float(xyxy[0]),
                        "y1": float(xyxy[1]),
                        "x2": float(xyxy[2]),
                        "y2": float(xyxy[3]),
                        "confidence": conf,
                    })

        # Lock released: `detections` now holds only plain Python floats,
        # safe to use while another request runs inference.
        return detections, inference_time_ms
