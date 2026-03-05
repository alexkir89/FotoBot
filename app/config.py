from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    result: set[int] = set()
    for part in raw.split(','):
        part = part.strip()
        if part:
            result.add(int(part))
    return result


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    ssl_root_cert: Path
    db_ssl_required: bool
    conf_auto_accept: float
    model_path: Path
    dataset_images: Path
    dataset_labels: Path
    dataset_review: Path
    admin_ids: set[int]
    default_admin_if_empty: bool
    products_csv: Path


def load_settings() -> Settings:
    bot_token = os.getenv('BOT_TOKEN', '')
    if not bot_token:
        raise RuntimeError('BOT_TOKEN is required')

    settings = Settings(
        bot_token=bot_token,
        db_host=os.getenv('DB_HOST', ''),
        db_port=int(os.getenv('DB_PORT', '5432')),
        db_name=os.getenv('DB_NAME', ''),
        db_user=os.getenv('DB_USER', ''),
        db_password=os.getenv('DB_PASSWORD', ''),
        ssl_root_cert=Path(os.getenv('SSL_ROOT_CERT', '/app/certs/root.crt')),
        db_ssl_required=os.getenv('DB_SSL_REQUIRED', '1') not in {'0', 'false', 'False'},
        conf_auto_accept=float(os.getenv('CONF_AUTO_ACCEPT', '0.85')),
        model_path=Path(os.getenv('MODEL_PATH', '/app/models/shelf.pt')),
        dataset_images=Path(os.getenv('DATASET_IMAGES', '/app/dataset/images')),
        dataset_labels=Path(os.getenv('DATASET_LABELS', '/app/dataset/labels')),
        dataset_review=Path(os.getenv('DATASET_REVIEW', '/app/dataset/review')),
        admin_ids=_parse_admin_ids(os.getenv('ADMIN_IDS')),
        default_admin_if_empty=os.getenv('DEFAULT_ADMIN_IF_EMPTY', '1') not in {'0', 'false', 'False'},
        products_csv=Path(os.getenv('PRODUCTS_CSV', '/app/dataset/products.csv')),
    )

    required = [settings.db_host, settings.db_name, settings.db_user, settings.db_password]
    if not all(required):
        raise RuntimeError('DB_HOST/DB_NAME/DB_USER/DB_PASSWORD are required')

    settings.dataset_images.mkdir(parents=True, exist_ok=True)
    settings.dataset_labels.mkdir(parents=True, exist_ok=True)
    settings.dataset_review.mkdir(parents=True, exist_ok=True)

    return settings
