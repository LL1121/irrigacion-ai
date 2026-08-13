#!/usr/bin/env bash
# Solo landing institucional (irrigacionmalargue.net / :8088).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/_deploy_common.sh"

deploy_init

echo "==> Rebuild + up site"
"${COMPOSE[@]}" build site
"${COMPOSE[@]}" up -d site
compose_ps

SITE_PORT="${SITE_PORT:-8088}"
echo
echo "Site listo:"
echo "  http://127.0.0.1:${SITE_PORT}/"
echo "  http://127.0.0.1:${SITE_PORT}/politicas-privacidad"
