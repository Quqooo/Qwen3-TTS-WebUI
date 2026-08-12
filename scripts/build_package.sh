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
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64|arm64) ARCH="arm64" ;;
esac
if ldd --version 2>/dev/null | grep -qi musl; then
    LIBC_TAG="-musl"
else
    GLIBC="$(ldd --version 2>/dev/null | head -n1 | grep -oP '\)\s*\K[\d.]+')"
    LIBC_TAG="-glibc${GLIBC}"
fi
ARTIFACT="Qwen3-TTS-WebUI-v${APP_VERSION}-linux-${ARCH}${LIBC_TAG}"
"$VENV_PY" -m PyInstaller --clean --noconfirm "packaging/Qwen3-TTS-WebUI.spec"

SIZE_MB=$(du -m "dist/${ARTIFACT}" | cut -f1)
echo
echo "Build completed: dist/${ARTIFACT} (${SIZE_MB} MB)"
