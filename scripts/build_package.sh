#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-build"
VENV_PY="$VENV/bin/python"

# build frontend
cd "$ROOT/frontend"
pnpm install
pnpm build
cd "$ROOT"

# prepare build env
if [ ! -x "$VENV_PY" ]; then
    python3 -m venv "$VENV"
fi
"$VENV_PY" -m pip install --disable-pip-version-check -q -e "$ROOT" pyinstaller

# package
APP_VERSION="$(grep -oP '^version\s*=\s*"\K[^"]+' "$ROOT/pyproject.toml")"
"$VENV_PY" -m PyInstaller --clean --noconfirm "packaging/Qwen3-TTS-WebUI.spec"

SIZE_MB=$(du -m "dist/Qwen3-TTS-WebUI-${APP_VERSION}" | cut -f1)
echo
echo "Build completed: dist/Qwen3-TTS-WebUI-${APP_VERSION} (${SIZE_MB} MB)"
