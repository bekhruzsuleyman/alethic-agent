#!/usr/bin/env bash
# macOS installer for Alethic Agent (standalone zero-Python install via curl or local bundle).
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
  SRC_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
else
  SRC_DIR=""
fi

APP_SUPPORT="$HOME/Library/Application Support/Alethic"
INSTALL_DIR="$APP_SUPPORT/app"
BIN_DIR=""
QUIET=0
NO_WEIGHTS=0
REPO_URL="https://github.com/bekhruzsuleyman/alethic-300m.git"
PKG_URL="https://github.com/bekhruzsuleyman/alethic-agent/releases/download/v0.1.0/alethic-agent-macos.pkg"

for arg in "$@"; do
  case "$arg" in
    --quiet|-q) QUIET=1 ;;
    --no-weights) NO_WEIGHTS=1 ;;
    --dir=*) INSTALL_DIR="${arg#--dir=}" ;;
  esac
done

pick_bin_dir() {
  if [ -d "/opt/homebrew/bin" ] && [ -w "/opt/homebrew/bin" ]; then
    BIN_DIR="/opt/homebrew/bin"
  elif [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    BIN_DIR="/usr/local/bin"
  else
    BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"
  fi
}

ensure_path_rc() {
  local dir="$1"
  case ":$PATH:" in
    *":$dir:"*) return 0 ;;
  esac
  local line="export PATH=\"$dir:\$PATH\""
  for rc in "$HOME/.zshrc" "$HOME/.bash_profile"; do
    touch "$rc"
    if ! grep -Fq "$dir" "$rc"; then
      printf '\n# Added by Alethic Agent installer\n%s\n' "$line" >> "$rc"
    fi
  done
  export PATH="$dir:$PATH"
}

find_python312() {
  for cand in python3.12 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>&1; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

install_from_dir() {
  local from_dir="$1"
  echo "Installing standalone Alethic Agent to $INSTALL_DIR ..."
  mkdir -p "$INSTALL_DIR"
  local saved_weights=""
  if [ -f "$INSTALL_DIR/model-sft3c.pt" ]; then
    saved_weights="$(mktemp -t alethic-weights)"
    mv "$INSTALL_DIR/model-sft3c.pt" "$saved_weights"
  fi
  rm -rf "$INSTALL_DIR/_internal" "$INSTALL_DIR/alethic" "$INSTALL_DIR/alethic-agent"
  cp -Rp "$from_dir/." "$INSTALL_DIR/"
  chmod +x "$INSTALL_DIR/alethic"
  if [ -n "$saved_weights" ] && [ -f "$saved_weights" ] && [ ! -f "$INSTALL_DIR/model-sft3c.pt" ]; then
    mv "$saved_weights" "$INSTALL_DIR/model-sft3c.pt"
  fi
  if [ -d "$from_dir/Alethic Agent.app" ] && [ -w "/Applications" ]; then
    rm -rf "/Applications/Alethic Agent.app"
    cp -Rp "$from_dir/Alethic Agent.app" "/Applications/Alethic Agent.app"
  fi
  pick_bin_dir
  ln -sf "$INSTALL_DIR/alethic" "$BIN_DIR/alethic"
  ensure_path_rc "$BIN_DIR"
  "$BIN_DIR/alethic" --selftest
  if [ "$NO_WEIGHTS" -eq 0 ] && [ ! -f "$INSTALL_DIR/model-sft3c.pt" ]; then
    echo "Downloading SFT-3c model weights (1.2 GB)..."
    "$BIN_DIR/alethic" --download-weights || echo "Warning: weight download did not complete; alethic will retry on first run."
  fi
}

install_from_pkg_release() {
  local tmp
  tmp="$(mktemp -d -t alethic-mac-pkg)"
  echo "Downloading standalone Alethic Agent for macOS (no Python required)..."
  curl -fL --progress-bar "$PKG_URL" -o "$tmp/alethic.pkg"
  pkgutil --expand-full "$tmp/alethic.pkg" "$tmp/expanded"
  local payload_dir
  payload_dir="$(find "$tmp/expanded" -type d -path "*/Library/Application Support/Alethic/app" | head -n 1)"
  if [ -z "$payload_dir" ] || [ ! -x "$payload_dir/alethic" ]; then
    rm -rf "$tmp"
    echo "Error: could not extract Alethic bundle from package." >&2
    return 1
  fi
  install_from_dir "$payload_dir"
  rm -rf "$tmp"
}

install_source_or_remote() {
  local py
  if ! py="$(find_python312)"; then
    echo "Python 3.12+ is required on Intel macOS (not found on PATH)."
    echo "Install it with Homebrew: brew install python@3.12"
    exit 1
  fi
  local venv="$APP_SUPPORT/venv"
  if [ ! -x "$venv/bin/python" ]; then
    echo "Creating isolated environment in $venv ..."
    "$py" -m venv "$venv"
  fi
  "$venv/bin/python" -m pip install --upgrade pip setuptools
  if [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/pyproject.toml" ]; then
    "$venv/bin/python" -m pip install -e "$SRC_DIR"
  else
    "$venv/bin/python" -m pip install --upgrade "git+$REPO_URL"
  fi
  pick_bin_dir
  ln -sf "$venv/bin/alethic" "$BIN_DIR/alethic"
  ensure_path_rc "$BIN_DIR"
  "$BIN_DIR/alethic" --selftest
  if [ "$NO_WEIGHTS" -eq 0 ]; then
    echo "Downloading SFT-3c model weights (1.2 GB)..."
    "$BIN_DIR/alethic" --download-weights || echo "Warning: weight download did not complete; alethic will retry on first run."
  fi
}

if [ -n "$SRC_DIR" ] && [ -x "$SRC_DIR/alethic" ] && [ -d "$SRC_DIR/_internal" ]; then
  install_from_dir "$SRC_DIR"
elif [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] && command -v pkgutil >/dev/null 2>&1; then
  install_from_pkg_release
else
  install_source_or_remote
fi

echo ""
echo "Alethic Agent is installed! Run: alethic"
if [ "$QUIET" -eq 0 ] && [ -t 0 ]; then
  read -r -p "Press Enter to close..." _
fi
