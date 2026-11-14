"""Pluggable agent brains. 'auto' prefers an external chat endpoint for planning when a key is present,
otherwise the deterministic rules planner; the local XON LM handles completion and simple edits."""
from __future__ import annotations

import os


def local_only(cfg: dict | None = None) -> bool:
    if os.environ.get("XON_LOCAL_ONLY") in ("0", "false"):
        return False
    if cfg is None:
        from xon import config
        cfg = config.load()
    return bool(cfg.get("xon", {}).get("local_only", True))


def pick(name: str = "auto", cfg: dict | None = None):
    if local_only(cfg):  # no cloud brains at all
        if name == "local":
            from .local import LocalBackend
            return LocalBackend()
        from .rules import RulesBackend
        return RulesBackend()
    if name in ("auto", "anthropic") and os.environ.get("ANTHROPIC_API_KEY"):
        from .anthropic_compat import AnthropicBackend
        return AnthropicBackend()
    if name in ("auto", "openai") and (os.environ.get("XON_OPENAI_KEY") or os.environ.get("OPENAI_API_KEY")):
        from .openai_compat import OpenAIBackend
        return OpenAIBackend()
    if name == "local":
        from .local import LocalBackend
        return LocalBackend()
    from .rules import RulesBackend
    return RulesBackend()
