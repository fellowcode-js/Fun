#!/usr/bin/env bash
# XON one-command install. Creates .venv, installs pinned deps (CPU torch unless a GPU is present), Chromium.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if ! $PY -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  echo "XON needs Python 3.10+. Fix: install it (e.g. 'uv python install 3.12') and re-run with PYTHON=python3.12"; exit 1
fi
if [ ! -d .venv ]; then $PY -m venv .venv; fi
. .venv/bin/activate
python -m pip install -q --upgrade pip
if command -v nvidia-smi >/dev/null 2>&1; then
  python -m pip install -q -r scripts/requirements.txt
else
  python -m pip install -q --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 || python -m pip install -q torch
  python -m pip install -q -r scripts/requirements.txt
fi
python -m pip install -q -e .
# headless browser for design tools (skipped if a system Chromium is found or XON_CHROMIUM is set)
if [ -z "${XON_CHROMIUM:-}" ] && [ ! -e /opt/pw-browsers/chromium ]; then
  python -m playwright install chromium || echo "WARN: Chromium install failed; design tools fall back to DOM-only checks"
fi
python scripts/build_evalsets.py >/dev/null || true
echo
echo "XON installed. Next:  source .venv/bin/activate && xon doctor && xon init && xon start --all"
