#!/usr/bin/env bash
# Solo imagen Docker del sandbox de skills (no toca API/DB/PWA).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

load_env

IMAGE="${SKILL_SANDBOX_IMAGE:-skill-sandbox-image}"
echo "==> Construyendo imagen de sandbox: $IMAGE"
docker build -t "$IMAGE" "$ROOT/backend/sandbox_env"
echo "OK $IMAGE"
echo "El API la usa si SKILL_EXECUTION_MODE=sandbox (no hace falta rebuild del API)."
