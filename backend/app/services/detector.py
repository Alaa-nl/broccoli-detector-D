"""
BroccoliDetector: loads the YOLOv8n model and runs detections.

This class wraps the Ultralytics YOLO model. We keep all
model-related code in one place so the rest of the app
does not need to know about Ultralytics.
"""

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

        # If the weights file is missing, we still want the app
        # to start so the team can develop the frontend without it.
        # In that case, predict() will return an empty list.
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

    def predict(
        self, image: Image.Image
    ) -> Tuple[List[dict], float]:
        """Run detection on one image.

        Args:
            image: A PIL image (RGB) loaded from the user upload.

        Returns:
            A tuple of (detections, inference_time_ms) where
            detections is a list of dicts with keys:
            'x1', 'y1', 'x2', 'y2', 'confidence'.
        """
        # If the model could not load, return an empty result.
        if self.model is None:
            return [], 0.0

        # Convert the PIL image to a NumPy array. YOLO accepts
        # both PIL and NumPy, but NumPy is a bit faster.
        img_array = np.array(image)

        # Measure how long inference takes (for the demo UI).
        start_time = time.time()

        # Run the model. We pass conf to filter out low-confidence
        # boxes and verbose=False to keep the terminal clean.
        results = self.model.predict(
            source=img_array,
            conf=self.conf_threshold,
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

        return detections, inference_time_ms
