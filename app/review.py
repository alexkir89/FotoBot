from __future__ import annotations

from pathlib import Path

from PIL import Image


def make_detection_crop(image_path: Path, out_path: Path, x1: int, y1: int, x2: int, y2: int) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as img:
        crop = img.crop((x1, y1, x2, y2))
        crop.save(out_path, format='JPEG')
    return out_path
