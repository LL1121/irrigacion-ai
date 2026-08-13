#!/usr/bin/env bash
# Solo Postgres. No reconstruye API/PWA/site.
# El schema nuevo lo aplica el API al arrancar (migrations_runtime).
# init.sql solo corre la primera vez que se crea el volumen.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

deploy_init

echo "==> Levantando db (sin rebuild de imágenes de app)"
"${COMPOSE[@]}" up -d db
wait_db
compose_ps

echo
echo "DB lista (irrigacion_db_prod)."
echo "Backup: ./scripts/backup_db.sh"
