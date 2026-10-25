"""Node heartbeats and status files (so any node, and the dashboard, can see the others)."""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

from xon import config


def heartbeat(cfg: dict, node: str, **info) -> None:
    d = config.path(cfg, "exchange") / "heartbeats"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"node": node, "pid": os.getpid(), "host": socket.gethostname(), "t": time.time(), **info}
    tmp = d / f"{node}.json.tmp"
    tmp.write_text(json.dumps(rec, default=str))
    tmp.replace(d / f"{node}.json")


def nodes(cfg: dict, stale_s: float = 120) -> list[dict]:
    d = config.path(cfg, "exchange") / "heartbeats"
    out = []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        r["alive"] = time.time() - r["t"] < stale_s
        out.append(r)
    return out
