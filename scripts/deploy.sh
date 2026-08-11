#!/usr/bin/env bash
# Deploy on-prem de irrigacion-bot (API + DB + imagen sandbox)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Falta $ENV_FILE"
  echo "  cp .env.production.example .env.production"
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

echo "==> Construyendo imagen de sandbox de skills"
docker build -t "${SKILL_SANDBOX_IMAGE:-skill-sandbox-image}" "$ROOT/backend/sandbox_env"

echo "==> Levantando stack de producción"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d

echo "==> Estado"
"${COMPOSE[@]}" ps

API_PORT="${API_PORT:-8000}"
echo
echo "Listo. Healthcheck:"
echo "  curl http://127.0.0.1:${API_PORT}/health"
echo
echo "En las PCs de escritorio, configurá la URL del servidor (Settings):"
echo "  http://<IP-DEL-SERVIDOR>:${API_PORT}"
