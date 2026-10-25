"""Pluggable agent brains. 'auto' prefers an external chat endpoint for planning when a key is present,
otherwise the deterministic rules planner; the local XON LM handles completion and simple edits."""
from __future__ import annotations

import os


def pick(name: str = "auto"):
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
