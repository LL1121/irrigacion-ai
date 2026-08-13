#!/usr/bin/env bash
# Deploy completo: db + sandbox + PWA + api + site.
# Para un cambio puntual usá el script del servicio (más rápido):
#   ./scripts/deploy_api.sh
#   ./scripts/deploy_frontend.sh
#   ./scripts/deploy_site.sh
#   ./scripts/deploy_db.sh
#   ./scripts/deploy_sandbox.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

deploy_init

"$ROOT/scripts/deploy_db.sh"
"$ROOT/scripts/deploy_sandbox.sh"
SKIP_API_RESTART=1 "$ROOT/scripts/deploy_frontend.sh"
"$ROOT/scripts/deploy_api.sh"
"$ROOT/scripts/deploy_site.sh"

PORT="${API_PORT:-8000}"
SITE_PORT="${SITE_PORT:-8088}"
PUBLIC="${API_PUBLIC_URL:-http://100.68.57.77:${PORT}}"
LAN="${LAN_API_URL:-http://172.30.12.101:${PORT}}"

echo
echo "════════════════════════════════════════════════════════════"
echo " Deploy completo listo"
echo "════════════════════════════════════════════════════════════"
echo
echo "API + health:"
echo "  curl http://127.0.0.1:${PORT}/health"
echo
echo "Landing institucional (apuntar irrigacionmalargue.net en Cloudflare):"
echo "  http://127.0.0.1:${SITE_PORT}/"
echo "  http://127.0.0.1:${SITE_PORT}/politicas-privacidad"
echo "  contenedor: irrigacion_site_prod  (red proxy-network)"
echo
echo "PWA / asistente (ia.irrigacionmalargue.net):"
echo "  ${PUBLIC}/"
echo "  ${LAN}/"
echo
echo "PCs de escritorio (Tauri — instalar binario, no usa la PWA):"
echo "  ./scripts/build_desktop.sh"
echo "  URL default del cliente: ${PUBLIC}"
echo
echo "Verificación rápida:"
echo "  curl -fsS http://127.0.0.1:${PORT}/health | head -c 200 && echo"
echo "  curl -fsS -o /dev/null -w 'PWA index: HTTP %{http_code}\\n' http://127.0.0.1:${PORT}/"
echo "  curl -fsS -o /dev/null -w 'manifest: HTTP %{http_code}\\n' http://127.0.0.1:${PORT}/manifest.webmanifest"
echo
echo "Deploys parciales:"
echo "  ./scripts/deploy_api.sh         # cambio de backend"
echo "  ./scripts/deploy_frontend.sh    # cambio de PWA"
echo "  ./scripts/deploy_site.sh        # landing / privacy"
echo "  ./scripts/deploy_db.sh          # solo Postgres"
echo "  ./scripts/deploy_sandbox.sh     # imagen de skills"
