from __future__ import annotations

from pathlib import Path

from PIL import Image


def yolo_line(class_id: int, x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> str:
    bw = max(x2 - x1, 1)
    bh = max(y2 - y1, 1)
    xc = x1 + bw / 2
    yc = y1 + bh / 2
    return f"{class_id} {xc / width:.6f} {yc / height:.6f} {bw / width:.6f} {bh / height:.6f}"


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size
