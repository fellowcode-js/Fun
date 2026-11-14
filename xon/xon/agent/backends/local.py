"""Local XON LM backend. Honest scope: completion and simple edits, not multi-step planning.
Planning requests are delegated to the rules planner."""
from __future__ import annotations

from .rules import RulesBackend


class LocalBackend(RulesBackend):
    name = "local+rules"
