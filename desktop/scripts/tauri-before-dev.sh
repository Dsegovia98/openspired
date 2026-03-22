#!/usr/bin/env bash
set -euo pipefail

DEV_URL="${TAURI_DEV_URL:-http://127.0.0.1:1420}"

if curl -fsS --max-time 2 "$DEV_URL" >/dev/null 2>&1; then
  echo "Reusing existing Vite dev server at ${DEV_URL}"
  exit 0
fi

npm run dev

