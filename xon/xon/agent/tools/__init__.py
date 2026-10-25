"""Agent tools. Each module defines SPEC (name, description, params) and run(ctx, **args) -> dict."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

MODULES = ["read", "write", "edit", "glob", "grep", "shell", "test", "git", "web_fetch", "view_image", "recognize",
           "complete", "design", "fix"]


@dataclass
class Context:
    root: Path
    cfg: dict
    artifacts: object | None = None
    _models: dict = field(default_factory=dict)

    def path(self, p: str) -> Path:
        from xon.agent.sandbox import jail
        return jail(self.root, p)

    def vision(self):
        if "vision" not in self._models:
            from xon import config
            p = config.path(self.cfg, "checkpoints") / "promoted" / "vision.pt"
            if p.exists():
                from xon.vision.train import load_model
                self._models["vision"] = load_model(p)
            else:
                self._models["vision"] = None
        return self._models["vision"]

    def lm(self):
        if "lm" not in self._models:
            from xon import config
            d = config.path(self.cfg, "checkpoints") / "promoted"
            if (d / "lm.pt").exists() and (d / "tokenizer.json").exists():
                from xon.lm.train import load_model
                from xon.tokenizer import BPETokenizer
                self._models["lm"] = (load_model(d / "lm.pt"), BPETokenizer.load(d / "tokenizer.json"))
            else:
                self._models["lm"] = (None, None)
        return self._models["lm"]


def registry() -> dict:
    out = {}
    for m in MODULES:
        mod = importlib.import_module(f"xon.agent.tools.{m}")
        out[mod.SPEC["name"]] = mod
    return out


def schemas() -> list[dict]:
    return [m.SPEC for m in registry().values()]
