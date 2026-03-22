# Openspired Desktop (Scaffold)

Desktop shell for Openspired built with Tauri + React.

## One-command launcher (recommended)

From repo root:

```bash
./openspired
```

This starts API + UI with minimal friction. Use `./openspired --desktop` to force Tauri mode.

## Dev

```bash
cd desktop
npm install
npm run tauri dev
```

## Build

```bash
cd desktop
npm run tauri build
```

For macOS release artifacts (`.app` + `.dmg`) use:

```bash
bash ../scripts/build-macos-installer.sh
```

For a signed + notarized macOS release:

```bash
bash ../scripts/setup-notary-profile.sh openspired-notary
MACOS_SIGN_IDENTITY="Developer ID Application: YOUR COMPANY (TEAMID1234)" \
MACOS_NOTARY_PROFILE="openspired-notary" \
bash ../scripts/build-macos-installer.sh --notarize
```

## Backend behavior (no terminal flow)

Desktop app now boots the local Python backend automatically on startup.

- No separate `run.py --serve-api` terminal is required for normal desktop usage.
- The app stores runtime data in the app data directory (`runtime/` with `.env`, `workspace/`, logs).
- The API token is auto-read and injected into the UI.

Manual API startup is still available for debugging:

```bash
python engine/run.py --serve-api
```
