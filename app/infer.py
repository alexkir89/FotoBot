from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ultralytics import YOLO

LOGGER = logging.getLogger(__name__)


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    class_id: int
    confidence: float


class Inferencer:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self._model: YOLO | None = None
        if model_path.exists():
            self._model = YOLO(str(model_path))
            LOGGER.info('Loaded model from %s', model_path)
        else:
            LOGGER.warning('Model not found at %s, running data collection mode', model_path)

    @property
    def enabled(self) -> bool:
        return self._model is not None

    def predict(self, image_path: Path) -> list[Detection]:
        if not self._model:
            return []
        results = self._model.predict(source=str(image_path), verbose=False)
        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                conf = float(box.conf[0])
                class_id = int(box.cls[0])
                detections.append(
                    Detection(x1=x1, y1=y1, x2=x2, y2=y2, class_id=class_id, confidence=conf)
                )
        return detections
