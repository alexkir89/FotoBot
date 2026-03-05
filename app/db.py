from __future__ import annotations

import ssl
from typing import Any

import asyncpg

from app.config import Settings


CREATE_SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS shelf_ai;

CREATE TABLE IF NOT EXISTS shelf_ai.products(
  id serial PRIMARY KEY,
  code text UNIQUE NOT NULL,
  name text NOT NULL,
  class_id int UNIQUE NOT NULL,
  is_our boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS shelf_ai.photos(
  id serial PRIMARY KEY,
  tg_user_id bigint NOT NULL,
  file_path text NOT NULL,
  created_at timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shelf_ai.detections(
  id serial PRIMARY KEY,
  photo_id int NOT NULL REFERENCES shelf_ai.photos(id) ON DELETE CASCADE,
  x1 int NOT NULL,
  y1 int NOT NULL,
  x2 int NOT NULL,
  y2 int NOT NULL,
  predicted_class_id int,
  predicted_name text,
  conf real NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  true_class_id int,
  true_name text,
  created_at timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shelf_ai.weak_labels(
  id serial PRIMARY KEY,
  photo_id int NOT NULL REFERENCES shelf_ai.photos(id) ON DELETE CASCADE,
  product_code text NOT NULL,
  qty int NOT NULL CHECK (qty >= 1),
  created_at timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_detections_status ON shelf_ai.detections(status);
CREATE INDEX IF NOT EXISTS idx_detections_photo_id ON shelf_ai.detections(photo_id);
CREATE INDEX IF NOT EXISTS idx_products_class_id ON shelf_ai.products(class_id);
"""


def build_ssl_context(settings: Settings) -> ssl.SSLContext | None:
    if not settings.db_ssl_required:
        return None
    return ssl.create_default_context(cafile=str(settings.ssl_root_cert))


async def connect_db(settings: Settings) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        ssl=build_ssl_context(settings),
        min_size=1,
        max_size=10,
    )
    async with pool.acquire() as conn:
        await conn.execute(CREATE_SCHEMA_SQL)
    return pool


async def get_products_map(conn: asyncpg.Connection) -> dict[int, dict[str, Any]]:
    rows = await conn.fetch('SELECT class_id, code, name, is_our FROM shelf_ai.products ORDER BY class_id')
    return {r['class_id']: dict(r) for r in rows}
