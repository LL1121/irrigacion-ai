#!/usr/bin/env bash
# Solo PWA (desktop-app/dist). El API la sirve por volumen; no rebuild de imagen.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

require_env_file
load_env

echo "==> Compilando PWA (desktop-app/dist)"
cd "$ROOT/desktop-app"
npm ci
npm run build
cd "$ROOT"

if [[ ! -f "$ROOT/desktop-app/dist/index.html" ]]; then
  echo "Error: no se generó desktop-app/dist/index.html"
  exit 1
fi

if [[ "${SKIP_API_RESTART:-}" == "1" ]]; then
  echo "==> Dist listo (restart api omitido; lo toma el deploy del API)"
elif api_running; then
  echo "==> Reiniciando api para tomar el dist nuevo"
  "${COMPOSE[@]}" restart api
  wait_api
else
  echo "==> API no está corriendo; dist listo. Después: ./scripts/deploy_api.sh"
fi

PORT="${API_PORT:-8000}"
echo
echo "Frontend listo (PWA en :${PORT}/)."
echo "  curl -fsS -o /dev/null -w 'PWA index: HTTP %{http_code}\\n' http://127.0.0.1:${PORT}/"
