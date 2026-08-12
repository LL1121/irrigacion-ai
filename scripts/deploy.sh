#!/usr/bin/env bash
# Deploy on-prem: PWA + API + PostgreSQL + imagen sandbox de skills
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Falta $ENV_FILE"
  echo "  cp .env.example .env"
  echo "  # editar secretos y volver a correr"
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

SKILL_HOST_DIR="${SKILL_HOST_DIR:-/var/lib/irrigacion/skills}"
echo "==> Preparando workspace de skills: $SKILL_HOST_DIR"
sudo mkdir -p "$SKILL_HOST_DIR"
sudo chmod 755 "$SKILL_HOST_DIR"

if [[ -z "${DOCKER_GID:-}" ]]; then
  if getent group docker >/dev/null 2>&1; then
    DOCKER_GID="$(getent group docker | cut -d: -f3)"
    export DOCKER_GID
    echo "==> DOCKER_GID detectado: $DOCKER_GID"
  else
    export DOCKER_GID=0
    echo "==> Advertencia: grupo docker no encontrado; DOCKER_GID=0"
  fi
fi

echo "==> Compilando PWA (desktop-app/dist)"
cd "$ROOT/desktop-app"
npm ci
npm run build
cd "$ROOT"

if [[ ! -f "$ROOT/desktop-app/dist/index.html" ]]; then
  echo "Error: no se generó desktop-app/dist/index.html"
  exit 1
fi

echo "==> Construyendo imagen de sandbox de skills"
docker build -t "${SKILL_SANDBOX_IMAGE:-skill-sandbox-image}" "$ROOT/backend/sandbox_env"

echo "==> Levantando stack de producción (db + api + PWA estática)"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d

echo "==> Esperando healthcheck del API…"
API_PORT="${API_PORT:-8000}"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Estado"
"${COMPOSE[@]}" ps

PUBLIC="${API_PUBLIC_URL:-http://100.68.57.77:${API_PORT}}"
LAN="${LAN_API_URL:-http://172.30.12.101:${API_PORT}}"

echo
echo "════════════════════════════════════════════════════════════"
echo " Deploy listo"
echo "════════════════════════════════════════════════════════════"
echo
echo "API + health:"
echo "  curl http://127.0.0.1:${API_PORT}/health"
echo
echo "PWA móvil (misma URL — agregar a pantalla de inicio):"
echo "  ${PUBLIC}/"
echo "  ${LAN}/"
echo
echo "PCs de escritorio (Tauri — instalar binario, no usa la PWA):"
echo "  ./scripts/build_desktop.sh"
echo "  URL default del cliente: ${PUBLIC}"
echo
echo "Verificación rápida:"
echo "  curl -fsS http://127.0.0.1:${API_PORT}/health | head -c 200 && echo"
echo "  curl -fsS -o /dev/null -w 'PWA index: HTTP %{http_code}\n' http://127.0.0.1:${API_PORT}/"
echo "  curl -fsS -o /dev/null -w 'manifest: HTTP %{http_code}\n' http://127.0.0.1:${API_PORT}/manifest.webmanifest"
