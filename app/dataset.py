from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path


def append_label_line(labels_dir: Path, image_stem: str, line: str) -> Path:
    label_path = labels_dir / f'{image_stem}.txt'
    with label_path.open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    return label_path


def export_dataset_archive(dataset_root: Path) -> Path:
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    out_path = dataset_root.parent / f'dataset_export_{ts}.tar.gz'
    with tarfile.open(out_path, 'w:gz') as tar:
        for rel in ['images', 'labels', 'data.yaml']:
            target = dataset_root / rel
            if target.exists():
                tar.add(target, arcname=f'dataset/{rel}')
    return out_path
