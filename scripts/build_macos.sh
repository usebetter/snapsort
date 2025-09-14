#!/usr/bin/env bash
set -euo pipefail

# Build macOS self-contained bundles via PyInstaller.
# Supports building native (arm64 on Apple Silicon) and x86_64 (Intel) via Rosetta.
#
# Usage:
#   scripts/build_macos.sh                 # build native arch only
#   scripts/build_macos.sh arm64           # build arm64 bundle
#   scripts/build_macos.sh x86_64          # build x86_64 bundle (requires Rosetta + x86_64 Python)
#   scripts/build_macos.sh both            # build both arm64 and x86_64
#
# Output: dist/snapsort-<arch>/ and snapsort-macos-<arch>.7z

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

ARCH_REQ="${1:-native}"

if [[ "$ARCH_REQ" == "native" ]]; then
  # Resolve to current machine arch
  ARCH_REQ="$(uname -m)"
fi

build_one() {
  local ARCH="$1"
  echo "[INFO] Building for $ARCH"

  local PY="python3"
  local PIP="python3 -m pip"
  local RUN=""

  if [[ "$ARCH" == "x86_64" ]]; then
    # Ensure Rosetta is available for Apple Silicon hosts
    if [[ "$(uname -m)" == "arm64" ]]; then
      if ! /usr/bin/pgrep oahd >/dev/null 2>&1; then
        echo "[INFO] Installing Rosetta (requires sudo)..."
        sudo softwareupdate --install-rosetta --agree-to-license || true
      fi
    fi
    RUN="arch -x86_64"
  elif [[ "$ARCH" != "arm64" ]]; then
    echo "[ERROR] Unsupported arch: $ARCH (expected arm64 or x86_64)" >&2
    exit 2
  fi

  # Create venv per-arch
  local VENV=".build/venv-$ARCH"
  rm -rf "$VENV"
  mkdir -p ".build"
  if [[ -n "$RUN" ]]; then
    $RUN $PY -m venv "$VENV"
  else
    $PY -m venv "$VENV"
  fi

  # Activate venv
  # shellcheck disable=SC1090
  source "$VENV/bin/activate"

  # Verify interpreter arch
  local DETECTED_ARCH
  DETECTED_ARCH=$(python -c 'import platform; print(platform.machine())')
  echo "[INFO] Python arch in venv: $DETECTED_ARCH"
  if [[ "$ARCH" == "x86_64" && "$DETECTED_ARCH" != "x86_64" ]]; then
    echo "[ERROR] Expected x86_64 Python under Rosetta. Install an x86_64 Python (e.g., python.org x86_64) and ensure \"arch -x86_64 python3\" works." >&2
    exit 3
  fi
  if [[ "$ARCH" == "arm64" && "$DETECTED_ARCH" != "arm64" ]]; then
    echo "[ERROR] Expected arm64 Python. Ensure native arm64 python3 is used." >&2
    exit 3
  fi

  # Install dependencies and PyInstaller
  python -m pip install -U pip wheel
  python -m pip install -e . pyinstaller

  # Build with PyInstaller (one-folder). Collect data for heavy deps.
  pyinstaller \
    --noconfirm --clean \
    --name snapsort \
    --paths src \
    --collect-all cv2 \
    --collect-all rawpy \
    --collect-all PIL \
    --collect-all imagehash \
    scripts/entry_snapsort.py

  # Move to arch-specific dist folder
  rm -rf "dist/snapsort-$ARCH"
  mkdir -p "dist/snapsort-$ARCH"
  mv dist/snapsort/* "dist/snapsort-$ARCH/" 2>/dev/null || true

  # Optional: code sign the bundle if CODESIGN_ID is provided
  if [[ -n "${CODESIGN_ID:-}" ]]; then
    echo "[INFO] Code signing with identity: $CODESIGN_ID"
    local ENTITLEMENTS_FILE="${ENTITLEMENTS_FILE:-scripts/entitlements.plist}"
    if [[ ! -f "$ENTITLEMENTS_FILE" ]]; then
      echo "[WARN] Entitlements file not found at $ENTITLEMENTS_FILE; proceeding without entitlements"
    fi
    # Sign nested libs first, then the main binary
    while IFS= read -r -d '' f; do
      codesign --force --options runtime --timestamp \
        ${ENTITLEMENTS_FILE:+--entitlements "$ENTITLEMENTS_FILE"} \
        --sign "$CODESIGN_ID" "$f"
    done < <(find "dist/snapsort-$ARCH" -type f \( -name "*.dylib" -o -name "*.so" -o -name "*.pyd" \) -print0)

    if [[ -x "dist/snapsort-$ARCH/snapsort" ]]; then
      codesign --force --options runtime --timestamp \
        ${ENTITLEMENTS_FILE:+--entitlements "$ENTITLEMENTS_FILE"} \
        --sign "$CODESIGN_ID" "dist/snapsort-$ARCH/snapsort"
    fi

    codesign --verify -v "dist/snapsort-$ARCH" || true
  fi

  # Optional: notarize and staple if NOTARIZE is set
  if [[ -n "${NOTARIZE:-}" ]]; then
    local DMG="snapsort-macos-$ARCH.dmg"
    echo "[INFO] Creating DMG $DMG for notarization"
    rm -f "$DMG"
    hdiutil create -fs APFS -volname "snapsort-$ARCH" -srcfolder "dist/snapsort-$ARCH" "$DMG"

    if [[ -n "${NOTARY_KEY_ID:-}" && -n "${NOTARY_ISSUER_ID:-}" && -n "${NOTARY_PRIVATE_KEY_B64:-}" ]]; then
      # Use App Store Connect API key in CI
      KEYFILE=".build/AuthKey_${NOTARY_KEY_ID}.p8"
      mkdir -p .build
      echo "$NOTARY_PRIVATE_KEY_B64" | base64 --decode > "$KEYFILE"
      echo "[INFO] Submitting to notarization with API key"
      xcrun notarytool submit "$DMG" --key "$KEYFILE" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" --wait
    elif [[ -n "${NOTARIZE_PROFILE:-}" ]]; then
      echo "[INFO] Submitting to notarization with keychain profile: $NOTARIZE_PROFILE"
      xcrun notarytool submit "$DMG" --keychain-profile "$NOTARIZE_PROFILE" --wait
    else
      echo "[WARN] NOTARIZE set but no credentials provided. Set NOTARIZE_PROFILE or NOTARY_KEY_ID/ISSUER_ID/PRIVATE_KEY_B64"
    fi

    echo "[INFO] Stapling ticket"
    xcrun stapler staple -v "$DMG" || true
  fi

  # Archive to 7z (or zip fallback)
  local ARCHIVE="snapsort-macos-$ARCH.7z"
  rm -f "$ARCHIVE"
  if command -v 7z >/dev/null 2>&1; then
    7z a "$ARCHIVE" ./dist/snapsort-$ARCH/* >/dev/null
    echo "[INFO] Wrote $ARCHIVE"
  else
    local ZIP="snapsort-macos-$ARCH.zip"
    rm -f "$ZIP"
    (cd dist && zip -qr "../$ZIP" "snapsort-$ARCH")
    echo "[INFO] 7z not found; wrote $ZIP instead"
  fi

  deactivate || true
}

case "$ARCH_REQ" in
  both)
    build_one arm64
    build_one x86_64
    ;;
  arm64|x86_64)
    build_one "$ARCH_REQ"
    ;;
  *)
    echo "[ERROR] Unknown argument: $ARCH_REQ (use: native|arm64|x86_64|both)" >&2
    exit 2
    ;;
esac
