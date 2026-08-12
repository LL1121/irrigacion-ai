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

cd "$ROOT/desktop-app"

echo "==> Compilando Tauri con VITE_API_BASE_URL=${VITE_API_BASE_URL}"
npm ci
npm run tauri build

echo
echo "Instaladores en desktop-app/src-tauri/target/release/bundle/"
ls -la src-tauri/target/release/bundle/*/ 2>/dev/null || ls -la src-tauri/target/release/bundle/
echo
echo "Distribuí el .deb / .AppImage / .rpm a las PCs de la oficina."
echo "El binario apunta por defecto a: ${VITE_API_BASE_URL}"
