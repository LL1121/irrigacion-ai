#!/usr/bin/env bash
# Publica artefactos firmados de Tauri en updates/ para el auto-updater.
#
# Uso (después de compilar con firma):
#   export TAURI_SIGNING_PRIVATE_KEY="$PWD/desktop-app/src-tauri/.tauri/irrigacion-bot.key"
#   ./scripts/build_desktop.sh
#   API_PUBLIC_URL=http://172.30.12.101:8000 ./scripts/publish_update.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$ROOT/desktop-app/src-tauri/target/release/bundle"
UPDATES="$ROOT/updates"
API_BASE="${API_PUBLIC_URL:-http://172.30.12.101:8000}"
API_BASE="${API_BASE%/}"

VERSION="$(node -p "require('$ROOT/desktop-app/src-tauri/tauri.conf.json').version")"
NOTES="${UPDATE_NOTES:-Actualización de Irrigación Bot v${VERSION}}"

mkdir -p "$UPDATES"

ARTIFACT="$(find "$BUNDLE/appimage" -maxdepth 1 -name '*.tar.gz' -type f 2>/dev/null | head -1 || true)"
if [[ -z "$ARTIFACT" || ! -f "$ARTIFACT" ]]; then
  echo "No se encontró *.tar.gz en $BUNDLE/appimage"
  echo "Compilá con AppImage para generar artefactos de updater:"
  echo "  cd desktop-app && npm run tauri build -- --bundles appimage"
  exit 1
fi

SIG_FILE="${ARTIFACT}.sig"
if [[ ! -f "$SIG_FILE" ]]; then
  echo "Falta la firma: $SIG_FILE"
  echo "Exportá TAURI_SIGNING_PRIVATE_KEY antes del build."
  exit 1
fi

BASENAME="$(basename "$ARTIFACT")"
cp -f "$ARTIFACT" "$UPDATES/$BASENAME"
SIGNATURE="$(tr -d '\n' < "$SIG_FILE")"
PUB_DATE="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
URL="${API_BASE}/updates/${BASENAME}"

python3 <<PY
import json
from pathlib import Path

manifest = {
    "version": "${VERSION}",
    "notes": """${NOTES}""",
    "pub_date": "${PUB_DATE}",
    "platforms": {
        "linux-x86_64": {
            "signature": """${SIGNATURE}""",
            "url": "${URL}",
        }
    },
}
Path("${UPDATES}/latest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo "Publicado en ${UPDATES}/"
echo "  - latest.json"
echo "  - ${BASENAME}"
echo "Manifiesto: ${API_BASE}/updates/latest.json"
