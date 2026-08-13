#!/usr/bin/env bash
# Helpers compartidos por scripts/deploy_*.sh (sourcear, no ejecutar).
# shellcheck disable=SC2034

if [[ -n "${_IRRIGACION_DEPLOY_COMMON:-}" ]]; then
  return 0
fi
_IRRIGACION_DEPLOY_COMMON=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-.env}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

require_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Falta $ENV_FILE"
    echo "  cp .env.example .env"
    echo "  # editar secretos y volver a correr"
    exit 1
  fi
}

load_env() {
  require_env_file
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
}

ensure_proxy_network() {
  local net="${PROXY_NETWORK:-proxy-network}"
  if ! docker network inspect "$net" >/dev/null 2>&1; then
    echo "==> Creando red externa '$net' (para nginx/proxy)"
    docker network create "$net"
  else
    echo "==> Red externa '$net' OK"
  fi
}

ensure_skill_dir() {
  local dir="${SKILL_HOST_DIR:-/var/lib/irrigacion/skills}"
  echo "==> Preparando workspace de skills: $dir"
  sudo mkdir -p "$dir"
  sudo chmod 755 "$dir"
}

detect_docker_gid() {
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
}

deploy_init() {
  load_env
  ensure_proxy_network
  ensure_skill_dir
  detect_docker_gid
}

wait_db() {
  echo "==> Esperando healthcheck de Postgres…"
  local i
  for i in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T db pg_isready \
      -U "${POSTGRES_USER:-postgres}" \
      -d "${POSTGRES_DB:-irrigacion_db}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timeout esperando la DB"
  "${COMPOSE[@]}" ps
  exit 1
}

wait_api() {
  local port="${API_PORT:-8000}"
  echo "==> Esperando healthcheck del API…"
  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timeout esperando el API"
  "${COMPOSE[@]}" ps
  exit 1
}

compose_ps() {
  echo "==> Estado"
  "${COMPOSE[@]}" ps
}

api_running() {
  docker inspect -f '{{.State.Running}}' irrigacion_api_prod 2>/dev/null | grep -q true
}
