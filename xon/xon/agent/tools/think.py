"""Scratchpad: the agent records observations, hypotheses and decisions; they land in artifacts/<task>/thoughts.md."""
import time

SPEC = {"name": "think", "description": "Write a reasoning note (observation, hypothesis, decision) to the task scratchpad; "
        "read=true returns all notes so far.", "params": {"note": "str?", "read": "bool?"}}


def run(ctx, note: str = "", read: bool = False) -> dict:
    d = ctx.artifacts.dir if ctx.artifacts is not None else ctx.root / ".xon"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "thoughts.md"
    if note:
        with open(f, "a") as fh:
            fh.write(f"- [{time.strftime('%H:%M:%S')}] {note}\n")
    return {"ok": True, "notes": f.read_text() if (read and f.exists()) else None}
