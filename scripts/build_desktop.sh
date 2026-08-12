#!/usr/bin/env bash
# Empaqueta el instalable Tauri para PCs de la oficina (cliente liviano al servidor)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

export VITE_API_BASE_URL="${API_PUBLIC_URL:-http://100.68.57.77:8000}"

KEY_DEFAULT="$ROOT/desktop-app/src-tauri/.tauri/irrigacion-bot.key"
if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" && -f "$KEY_DEFAULT" ]]; then
  export TAURI_SIGNING_PRIVATE_KEY="$KEY_DEFAULT"
fi

cd "$ROOT/desktop-app"

echo "==> Compilando Tauri con VITE_API_BASE_URL=${VITE_API_BASE_URL}"
if [[ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "==> Firma de updates: habilitada"
else
  echo "==> AVISO: TAURI_SIGNING_PRIVATE_KEY no definida; no se generarán .sig para el updater"
fi

npm ci
npm run tauri build -- --bundles deb,appimage

echo
echo "Instaladores en desktop-app/src-tauri/target/release/bundle/"
ls -la src-tauri/target/release/bundle/*/ 2>/dev/null || ls -la src-tauri/target/release/bundle/
echo
echo "Distribuí el .deb a las PCs de la oficina."
echo "Para publicar update OTA: API_PUBLIC_URL=${VITE_API_BASE_URL} ../scripts/publish_update.sh"
echo "Ver UPDATES.md para el flujo completo."
