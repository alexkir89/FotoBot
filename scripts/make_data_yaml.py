#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import yaml
from dotenv import load_dotenv

from app.config import load_settings
from app.db import build_ssl_context


async def run() -> None:
    settings = load_settings()
    ssl_ctx = build_ssl_context(settings)
    conn = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        ssl=ssl_ctx,
    )
    rows = await conn.fetch('SELECT class_id, code FROM shelf_ai.products ORDER BY class_id')
    await conn.close()
    if not rows:
        raise SystemExit('No products in shelf_ai.products')

    max_id = max(r['class_id'] for r in rows)
    names = {i: '' for i in range(max_id + 1)}
    for r in rows:
        names[r['class_id']] = r['code']

    dataset_root = settings.dataset_images.parent
    data = {
        'path': str(dataset_root),
        'train': 'images',
        'val': 'images',
        'names': names,
    }
    out = Path(dataset_root) / 'data.yaml'
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print(f'Written {out}')


if __name__ == '__main__':
    load_dotenv()
    asyncio.run(run())
