#!/usr/bin/env bash
# XON one-command install (Linux, macOS, WSL). Creates .venv, installs pinned deps (CPU torch unless an NVIDIA GPU
# is present), the headless browser, the frozen eval sets, and pre-downloads the local coder model (~1 GB).
#   XON_SKIP_MODEL=1 ./scripts/setup.sh     skip the model download (XON then uses only its own small LM)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
if ! command -v "$PY" >/dev/null 2>&1 || ! "$PY" -c 'import sys; assert sys.version_info >= (3,10)' 2>/dev/null; then
  echo "XON needs Python 3.10+."
  echo "Fix: macOS 'brew install python@3.12', Ubuntu 'sudo apt install python3 python3-venv', or https://python.org"
  echo "     then re-run, e.g. PYTHON=python3.12 ./scripts/setup.sh"; exit 1
fi
if ! "$PY" -c 'import venv, ensurepip' 2>/dev/null; then
  echo "Python's venv module is missing. Fix (Ubuntu/Debian): sudo apt install python3-venv"; exit 1
fi
say "creating virtual environment .venv"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q --upgrade pip
say "installing PyTorch"
if command -v nvidia-smi >/dev/null 2>&1; then
  python -m pip install -q torch                      # CUDA wheel from PyPI
elif [ "$(uname)" = "Darwin" ]; then
  python -m pip install -q torch                      # macOS wheels include Apple MPS support
else
  python -m pip install -q --index-url https://download.pytorch.org/whl/cpu torch || python -m pip install -q torch
fi
say "installing XON and its dependencies"
python -m pip install -q -r scripts/requirements.txt
python -m pip install -q -e .
if [ -z "${XON_CHROMIUM:-}" ] && [ ! -e /opt/pw-browsers/chromium ]; then
  say "installing headless Chromium (design tools, screenshots)"
  python -m playwright install chromium || echo "WARN: Chromium install failed; design tools fall back to DOM-only checks"
fi
python scripts/build_evalsets.py >/dev/null || true
if [ "${XON_SKIP_MODEL:-0}" != "1" ]; then
  say "downloading the local coder model (Qwen2.5-Coder-0.5B-Instruct, Apache-2.0, ~1 GB)"
  python - <<'PY' || echo "WARN: model download failed; it will retry on first use (or set [lm] init = \"scratch\")"
from xon import config
from xon.lm.pretrained import DEFAULT, PretrainedCoder
cfg = config.load()
c = PretrainedCoder(cfg["lm"].get("pretrained", DEFAULT), cache_dir=config.path(cfg, "checkpoints") / "pretrained")
print("model OK:", c.generate("def add(a, b):\n    return", max_new=4)[0].strip() or "(loaded)")
PY
fi
cat <<MSG

XON installed.
  source .venv/bin/activate
  xon doctor                          # check everything
  xon studio --open                   # the app (local model, no API key needed)
  claude mcp add xon -- $PWD/.venv/bin/xon mcp --root $PWD
                                      # let Claude Code use XON (free with your Claude login)
  xon init && xon start --all         # optional: let XON crawl + train itself
MSG
