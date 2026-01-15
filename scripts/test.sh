#!/usr/bin/env bash
set -euo pipefail

# Jump to repo root no matter where the script is called from
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
PY="$ROOT_DIR/$VENV_DIR/bin/python"

echo "==> Using python: $PY"
ls -la "$ROOT_DIR/$VENV_DIR/bin/python" || true

if [ ! -x "$PY" ]; then
  echo "==> Creating venv at $VENV_DIR"
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
  "$PY" -m pip install -U pip
fi

echo "==> Running classifier tests"
pushd classifier >/dev/null
"$PY" -m pip install -r requirements.txt -r requirements-dev.txt
"$PY" -m pytest -q
popd >/dev/null

echo "==> Running router tests"
pushd router >/dev/null
"$PY" -m pip install -r requirements.txt -r requirements-dev.txt
"$PY" -m pytest -q
popd >/dev/null

echo "DONE ✅ Tests passed"
