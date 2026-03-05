#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/best.pt [prod|dev]"
  exit 1
fi

SRC="$1"
MODE="${2:-prod}"

if [[ ! -f "$SRC" ]]; then
  echo "Weight file not found: $SRC"
  exit 1
fi

mkdir -p ./models
cp "$SRC" ./models/shelf.pt

echo "Installed weights to ./models/shelf.pt"

if [[ "$MODE" == "dev" ]]; then
  docker compose -f docker-compose.dev.yml restart bot
else
  docker compose -f docker-compose.prod.yml restart bot
fi
