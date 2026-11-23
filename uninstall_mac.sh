#!/usr/bin/env bash
# Uninstall Alethic Agent from macOS. Pass --purge to also remove downloaded weights.
set -euo pipefail

APP_SUPPORT="$HOME/Library/Application Support/Alethic"
DATA_DIR="$HOME/Library/Application Support/alethic-agent"
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
  esac
done

for bin in /usr/local/bin/alethic /opt/homebrew/bin/alethic "$HOME/.local/bin/alethic"; do
  if [ -L "$bin" ] || [ -f "$bin" ]; then
    rm -f "$bin" 2>/dev/null || true
  fi
done

rm -rf "$APP_SUPPORT" "/Applications/Alethic Agent.app" 2>/dev/null || true

if [ "$PURGE" -eq 1 ]; then
  rm -rf "$DATA_DIR" 2>/dev/null || true
  echo "Removed Alethic Agent and cached model weights."
else
  echo "Removed Alethic Agent (kept cached weights in $DATA_DIR; pass --purge to delete them)."
fi
