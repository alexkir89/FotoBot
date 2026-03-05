from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PriceTagDetection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


@dataclass
class OCRResult:
    text: str
    confidence: float


class PricePipeline:
    """Stage-2 skeleton: price-tag detection + OCR + SKU matching by geometry."""

    def detect_price_tags(self, image_path: Path) -> list[PriceTagDetection]:
        _ = image_path
        return []

    def recognize_price(self, crop_path: Path) -> OCRResult | None:
        _ = crop_path
        return None

    def assign_tags_to_sku(self, sku_boxes: list[tuple[int, int, int, int]], tag_boxes: list[PriceTagDetection]) -> dict[int, OCRResult]:
        _ = sku_boxes, tag_boxes
        return {}
