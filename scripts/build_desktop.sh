#!/usr/bin/env bash
# Empaqueta el instalable Tauri para PCs de la oficina
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/desktop-app"

npm install
npm run tauri build

echo
echo "Artefactos en desktop-app/src-tauri/target/release/bundle/"
ls -la src-tauri/target/release/bundle/*/ 2>/dev/null || ls -la src-tauri/target/release/bundle/
