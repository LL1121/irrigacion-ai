#!/usr/bin/env bash
# Rebuild + restart solo del API. No toca PWA, site ni sandbox.
# Asegura que la DB esté arriba (no la recrea).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

deploy_init

echo "==> Asegurando db"
"${COMPOSE[@]}" up -d db
wait_db

echo "==> Rebuild + up api"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d api
wait_api
compose_ps

PORT="${API_PORT:-8000}"
echo
echo "API listo: curl http://127.0.0.1:${PORT}/health"
echo "PWA montada desde desktop-app/dist (si no hay build, ./scripts/deploy_frontend.sh)"
