"""git with checkpoints and undo. Checkpoints are commits on the current branch tagged in the message."""
from xon.agent.sandbox import run_shell

SPEC = {"name": "git", "description": "git status | diff | checkpoint <msg> | undo | log | branch <name>",
        "params": {"action": "str", "arg": "str?"}}


def _g(ctx, args: str) -> dict:
    r = run_shell(f"git {args}", ctx.root, timeout=60)
    r["ok"] = r["code"] == 0
    return r


def run(ctx, action: str, arg: str = "") -> dict:
    if action == "status":
        return _g(ctx, "status --short")
    if action == "diff":
        return _g(ctx, f"diff {arg}".strip())
    if action == "log":
        return _g(ctx, "log --oneline -15")
    if action == "checkpoint":
        _g(ctx, "add -A")
        msg = (arg or "checkpoint").replace('"', "'")
        r = _g(ctx, f'commit -q --allow-empty -m "xon-checkpoint: {msg}"')
        return r
    if action == "undo":
        last = _g(ctx, "log -1 --pretty=%s")
        if not last["stdout"].startswith("xon-checkpoint"):
            return {"ok": False, "error": "last commit is not an XON checkpoint; refusing to undo"}
        return _g(ctx, "reset -q --hard HEAD~1")
    if action == "branch":
        return _g(ctx, f"checkout -q -b {arg}")
    return {"ok": False, "error": f"unknown git action {action}"}
