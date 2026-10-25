"""Agent tools. Each module defines SPEC (name, description, params) and run(ctx, **args) -> dict."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

MODULES = ["read", "write", "edit", "glob", "grep", "shell", "test", "git", "web_fetch", "view_image", "recognize",
           "complete", "design", "fix", "python_run", "cpp_build", "lint", "sqlite", "serve", "patch", "think", "docs_search", "codegen"]


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

    def pretrained(self):
        """Warm-start code model (Qwen2.5-Coder-0.5B-Instruct by default) or None."""
        if "pretrained" not in self._models:
            try:
                from xon.lm.pretrained import load
                self._models["pretrained"] = load(self.cfg)
            except Exception:
                self._models["pretrained"] = None
        return self._models["pretrained"]

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
