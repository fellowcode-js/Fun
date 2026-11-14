"""Per-task artifacts: artifacts/<task-id>/{plan.md, diff.patch, log.jsonl, status.json, screenshots/}."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path


def task_id(task: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:32] or "task"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"


class Artifacts:
    def __init__(self, root: Path, tid: str):
        self.dir = Path(root) / "artifacts" / tid
        (self.dir / "screenshots").mkdir(parents=True, exist_ok=True)
        self.id = tid

    def write(self, name: str, content: str) -> Path:
        p = self.dir / name
        p.write_text(content)
        return p

    def log(self, rec: dict) -> None:
        with open(self.dir / "log.jsonl", "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), **rec}, default=str) + "\n")

    def status(self, **kw) -> None:
        p = self.dir / "status.json"
        cur = json.loads(p.read_text()) if p.exists() else {}
        cur.update(kw)
        p.write_text(json.dumps(cur, indent=1, default=str))

    def screenshot_path(self, name: str) -> Path:
        return self.dir / "screenshots" / name
