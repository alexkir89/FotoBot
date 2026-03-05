#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from app.config import load_settings
from app.dataset import export_dataset_archive


if __name__ == '__main__':
    load_dotenv()
    settings = load_settings()
    dataset_root = settings.dataset_images.parent
    out = export_dataset_archive(Path(dataset_root))
    print(out)
