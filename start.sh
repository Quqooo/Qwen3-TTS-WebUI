#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
VENV_PY="$VENV/bin/python"
VENV_PIP="$VENV/bin/pip"
FRONTEND="$ROOT/frontend"
STATIC="$ROOT/backend/static"

if [ ! -f "$VENV_PY" ]; then
    python3 -m venv "$VENV"
fi

"$VENV_PIP" install -e "$ROOT" > /dev/null 2>&1

if [ ! -d "$FRONTEND/node_modules" ]; then
    (cd "$FRONTEND" && pnpm install)
fi

if [ ! -f "$STATIC/index.html" ] || [ -n "$(find "$FRONTEND/src" "$FRONTEND/public" "$FRONTEND/index.html" "$FRONTEND/package.json" -newer "$STATIC/index.html" -type f 2>/dev/null)" ]; then
    (cd "$FRONTEND" && pnpm build)
fi

exec "$VENV_PY" -m uvicorn backend.main:app --port 8000 --host localhost
