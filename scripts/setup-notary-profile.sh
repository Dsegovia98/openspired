#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only runs on macOS."
  exit 1
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo "Missing required command: xcrun"
  exit 1
fi

if ! xcrun --find notarytool >/dev/null 2>&1; then
  echo "notarytool was not found. Install Xcode command line tools."
  exit 1
fi

PROFILE_NAME="${1:-openspired-notary}"

echo "Creating notarytool keychain profile: $PROFILE_NAME"
echo "You will be prompted for:"
echo "  - Apple ID email"
echo "  - Team ID"
echo "  - App-specific password"
echo ""

xcrun notarytool store-credentials "$PROFILE_NAME"

echo ""
echo "Profile created."
echo "Use it in release builds with:"
echo "  MACOS_NOTARY_PROFILE=$PROFILE_NAME bash scripts/build-macos-installer.sh --notarize"

