#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$ROOT_DIR/desktop"
TAURI_DIR="$DESKTOP_DIR/src-tauri"
BUNDLE_APP_DIR="$TAURI_DIR/target/release/bundle/macos"
OUTPUT_DIR="$ROOT_DIR/dist/macos"

SIGN_ENABLED=0
NOTARIZE_ENABLED=0
SIGN_IDENTITY="${MACOS_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${MACOS_NOTARY_PROFILE:-}"

usage() {
  cat <<'EOF'
Build macOS release artifacts for Openspired Desktop.

Usage:
  bash scripts/build-macos-installer.sh [options]

Options:
  --sign                         Sign .app and .dmg with Developer ID cert
  --notarize                     Submit signed .dmg to Apple notary service and staple ticket
  --identity "<cert name>"       Override signing identity (or use MACOS_SIGN_IDENTITY)
  --notary-profile "<profile>"   Override keychain profile (or use MACOS_NOTARY_PROFILE)
  -h, --help                     Show this help

Examples:
  bash scripts/build-macos-installer.sh
  MACOS_SIGN_IDENTITY="Developer ID Application: ACME, INC. (TEAMID1234)" \
    bash scripts/build-macos-installer.sh --sign
  MACOS_SIGN_IDENTITY="Developer ID Application: ACME, INC. (TEAMID1234)" \
  MACOS_NOTARY_PROFILE="openspired-notary" \
    bash scripts/build-macos-installer.sh --notarize
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sign)
      SIGN_ENABLED=1
      shift
      ;;
    --notarize)
      NOTARIZE_ENABLED=1
      SIGN_ENABLED=1
      shift
      ;;
    --identity)
      SIGN_IDENTITY="${2:-}"
      shift 2
      ;;
    --notary-profile)
      NOTARY_PROFILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only runs on macOS."
  exit 1
fi

for cmd in npm cargo hdiutil python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

if [[ "$SIGN_ENABLED" -eq 1 ]]; then
  if ! command -v codesign >/dev/null 2>&1; then
    echo "Missing required command: codesign"
    exit 1
  fi
  if [[ -z "$SIGN_IDENTITY" ]]; then
    echo "Signing is enabled but no identity was provided."
    echo "Use --identity or export MACOS_SIGN_IDENTITY."
    echo "Tip: security find-identity -v -p codesigning"
    exit 1
  fi
fi

if [[ "$NOTARIZE_ENABLED" -eq 1 ]]; then
  if ! command -v xcrun >/dev/null 2>&1; then
    echo "Missing required command: xcrun"
    exit 1
  fi
  if [[ -z "$NOTARY_PROFILE" ]]; then
    echo "Notarization is enabled but no keychain profile was provided."
    echo "Use --notary-profile or export MACOS_NOTARY_PROFILE."
    echo "Tip: xcrun notarytool store-credentials <profile> --apple-id ... --team-id ... --password ..."
    exit 1
  fi
fi

echo "==> Installing desktop dependencies (if needed)"
if [[ ! -d "$DESKTOP_DIR/node_modules" ]]; then
  npm --prefix "$DESKTOP_DIR" install
fi

echo "==> Building macOS .app bundle with Tauri"
(cd "$DESKTOP_DIR" && npm run tauri build -- --bundles app)

APP_PATH="$(find "$BUNDLE_APP_DIR" -maxdepth 1 -type d -name "*.app" | head -n 1)"
if [[ -z "$APP_PATH" ]]; then
  echo "Could not find generated .app bundle in $BUNDLE_APP_DIR"
  exit 1
fi

VERSION="$(python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path("$TAURI_DIR/tauri.conf.json").read_text(encoding="utf-8"))
print(cfg.get("version", "0.0.0"))
PY
)"

mkdir -p "$OUTPUT_DIR"

DIST_APP_PATH="$OUTPUT_DIR/Openspired Desktop.app"
rm -rf "$DIST_APP_PATH"
cp -R "$APP_PATH" "$DIST_APP_PATH"

if [[ "$SIGN_ENABLED" -eq 1 ]]; then
  echo "==> Signing app bundle"
  codesign --force --deep --options runtime --timestamp --sign "$SIGN_IDENTITY" "$DIST_APP_PATH"
  codesign --verify --deep --strict --verbose=2 "$DIST_APP_PATH"
fi

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/openspired-dmg-stage.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT

cp -R "$DIST_APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

DMG_PATH="$OUTPUT_DIR/Openspired-Desktop_${VERSION}_macOS.dmg"
rm -f "$DMG_PATH"

echo "==> Creating DMG"
hdiutil create \
  -volname "Openspired Desktop" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH" >/dev/null

if [[ "$SIGN_ENABLED" -eq 1 ]]; then
  echo "==> Signing DMG"
  codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG_PATH"
  codesign --verify --verbose=2 "$DMG_PATH"
fi

if [[ "$NOTARIZE_ENABLED" -eq 1 ]]; then
  echo "==> Submitting DMG for notarization"
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
  echo "==> Stapling notarization ticket"
  xcrun stapler staple "$DMG_PATH"
  xcrun stapler validate "$DMG_PATH"
fi

echo ""
echo "Done."
echo "APP: $DIST_APP_PATH"
echo "DMG: $DMG_PATH"
