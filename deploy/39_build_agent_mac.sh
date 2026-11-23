#!/usr/bin/env bash
# Build standalone macOS installers (no Python or PyTorch needed by end users):
#   dist/alethic-agent-macos.pkg   (native macOS GUI Installer wizard)
#   dist/alethic-agent-macos.dmg   (drag-and-drop + double-click Install Alethic.command)
# Run on macOS (Apple Silicon or Intel).
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONUTF8=1
export PYTHONPATH=src

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3.12 || command -v python3)"
fi

echo "Building standalone macOS Alethic harness (no Python/PyTorch needed by users)..."
SAVED_WEIGHTS=""
if [ -f "dist/alethic-agent/model-sft3c.pt" ] && [ ! -f "runs_sft3c/model.pt" ]; then
  SAVED_WEIGHTS="$(mktemp -t alethic-saved-sft3c)"
  mv "dist/alethic-agent/model-sft3c.pt" "$SAVED_WEIGHTS"
fi

"$PY" -m pip install --quiet pyinstaller
"$PY" -m PyInstaller --noconfirm --clean alethic-agent.spec

echo "Checking embedded libraries and embedded Python..."
dist/alethic-agent/alethic --selftest
dist/alethic-agent/alethic --run-python -c "import csv, json, unittest, sqlite3, statistics; print('embedded python ok')"

cp install_mac.sh dist/alethic-agent/install_mac.sh
cp uninstall_mac.sh dist/alethic-agent/uninstall_mac.sh
cp install_mac.sh "dist/alethic-agent/Install Alethic.command"
chmod +x dist/alethic-agent/install_mac.sh dist/alethic-agent/uninstall_mac.sh "dist/alethic-agent/Install Alethic.command"

PKG_ROOT="build/pkg_root"
PKG_SCRIPTS="build/pkg_scripts"
rm -rf "$PKG_ROOT" "$PKG_SCRIPTS"
mkdir -p "$PKG_ROOT/Library/Application Support/Alethic/app" "$PKG_ROOT/etc/paths.d" "$PKG_SCRIPTS"
cp -R dist/alethic-agent/* "$PKG_ROOT/Library/Application Support/Alethic/app/"
echo "/Library/Application Support/Alethic/app" > "$PKG_ROOT/etc/paths.d/alethic"

cat > "$PKG_SCRIPTS/postinstall" <<'POST'
#!/usr/bin/env bash
chmod +x "/Library/Application Support/Alethic/app/alethic"
mkdir -p /usr/local/bin
ln -sf "/Library/Application Support/Alethic/app/alethic" /usr/local/bin/alethic
"/Library/Application Support/Alethic/app/alethic" --download-weights || true
exit 0
POST
chmod +x "$PKG_SCRIPTS/postinstall"

if command -v pkgbuild >/dev/null 2>&1 && command -v productbuild >/dev/null 2>&1; then
  echo "Building macOS GUI installer dist/alethic-agent-macos.pkg ..."
  pkgbuild --root "$PKG_ROOT" \
    --scripts "$PKG_SCRIPTS" \
    --identifier "com.alethic.agent" \
    --version "0.1.0" \
    --install-location "/" \
    "build/alethic-agent-component.pkg"
  productbuild --package "build/alethic-agent-component.pkg" "dist/alethic-agent-macos.pkg"
fi

if command -v hdiutil >/dev/null 2>&1; then
  echo "Building macOS disk image dist/alethic-agent-macos.dmg ..."
  DMG_STAGE="build/dmg_stage"
  rm -rf "$DMG_STAGE"
  mkdir -p "$DMG_STAGE"
  cp -R dist/alethic-agent/* "$DMG_STAGE/"
  if [ -d "dist/Alethic Agent.app" ]; then
    cp -R "dist/Alethic Agent.app" "$DMG_STAGE/"
  fi
  ln -s /Applications "$DMG_STAGE/Applications"
  rm -f dist/alethic-agent-macos.dmg
  hdiutil create -volname "Alethic Agent" -srcfolder "$DMG_STAGE" -ov -format UDZO dist/alethic-agent-macos.dmg
fi

if [ -n "$SAVED_WEIGHTS" ] && [ -f "$SAVED_WEIGHTS" ]; then
  mv "$SAVED_WEIGHTS" "dist/alethic-agent/model-sft3c.pt"
elif [ -f "runs_sft3c/model.pt" ]; then
  cp runs_sft3c/model.pt dist/alethic-agent/model-sft3c.pt
fi

echo ""
echo "Done!"
echo "  macOS GUI Installer (.pkg): dist/alethic-agent-macos.pkg"
echo "  macOS Disk Image (.dmg):    dist/alethic-agent-macos.dmg"
