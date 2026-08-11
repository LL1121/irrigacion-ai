#!/usr/bin/env bash
# Backup lógico de Postgres de producción
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)
OUT_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$OUT_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$OUT_DIR/irrigacion_db_${STAMP}.sql.gz"

echo "==> Dump a $OUT_FILE"
"${COMPOSE[@]}" exec -T db \
  pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-irrigacion_db}" \
  | gzip -c > "$OUT_FILE"

echo "OK ($(du -h "$OUT_FILE" | cut -f1))"
