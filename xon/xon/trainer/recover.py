"""Auto-recovery shared by LM and vision training: OOM, NaN loss, preemption (SIGTERM), checkpoints."""
from __future__ import annotations

import math
import os
import signal
import time
from pathlib import Path

import torch

from xon import config

log = config.log("recover")


class FaultInjector:
    """Deterministic fault injection for tests: {'oom_at': step, 'nan_at': step, 'sigterm_at': step}."""

    def __init__(self, spec: dict | None = None):
        self.spec = dict(spec or {})
        env = os.environ.get("XON_INJECT", "")
        for kv in filter(None, env.split(",")):
            k, v = kv.split("=")
            self.spec[k] = int(v)
        self.fired: set[str] = set()

    def check(self, step: int, kind: str) -> bool:
        if self.spec.get(f"{kind}_at") == step and kind not in self.fired:
            self.fired.add(kind)
            return True
        return False


class Preemption:
    """Sets a flag on SIGTERM/SIGINT so the loop checkpoints and exits cleanly (spot instances)."""

    def __init__(self):
        self.flag = False
        self._old = {}

    def __enter__(self):
        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                self._old[s] = signal.signal(s, self._handle)
            except ValueError:  # not main thread
                pass
        return self

    def _handle(self, signum, frame):
        log.warning(f"signal {signum}: checkpointing then exiting")
        self.flag = True

    def __exit__(self, *a):
        for s, h in self._old.items():
            signal.signal(s, h)


def is_oom(e: BaseException) -> bool:
    return isinstance(e, torch.cuda.OutOfMemoryError) or "out of memory" in str(e).lower()


def bad_loss(loss: torch.Tensor | float) -> bool:
    v = float(loss)
    return math.isnan(v) or math.isinf(v)


def save_ckpt(path: Path, **state) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    torch.save(state, tmp)
    os.replace(tmp, path)  # atomic: a crash never leaves a half checkpoint


def load_ckpt(path: Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return torch.load(path, map_location="cpu", weights_only=False)
    except Exception as e:
        log.warning(f"corrupt checkpoint {path}: {e}")
        return None


class CheckpointTimer:
    def __init__(self, minutes: float):
        self.every = minutes * 60
        self.last = time.time()

    def due(self) -> bool:
        if time.time() - self.last >= self.every:
            self.last = time.time()
            return True
        return False
