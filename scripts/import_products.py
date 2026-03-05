#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import csv
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from app.config import load_settings
from app.db import CREATE_SCHEMA_SQL, build_ssl_context


async def run(csv_path: Path) -> None:
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
    await conn.execute(CREATE_SCHEMA_SQL)
    count = 0
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            await conn.execute(
                """
                INSERT INTO shelf_ai.products(code, name, class_id, is_our)
                VALUES($1, $2, $3, $4)
                ON CONFLICT (code)
                DO UPDATE SET name=EXCLUDED.name, class_id=EXCLUDED.class_id, is_our=EXCLUDED.is_our
                """,
                row['code'].strip(),
                row['name'].strip(),
                int(row['class_id']),
                row.get('is_our', '1').strip() in {'1', 'true', 'True'},
            )
            count += 1
    await conn.close()
    print(f'Imported/updated {count} products from {csv_path}')


if __name__ == '__main__':
    load_dotenv()
    settings = load_settings()
    csv_path = Path(settings.products_csv)
    if not csv_path.exists():
        raise SystemExit(f'CSV not found: {csv_path}')
    asyncio.run(run(csv_path))
