"""Slash commands for the interactive `xon` REPL: /plan /run /review /test /diff /undo /agents /spawn /crawl
/train /design /status (+ /help, /quit)."""
from __future__ import annotations

import json
import shlex
from pathlib import Path

COMMANDS: dict[str, tuple] = {}


def command(name: str, help_: str):
    def deco(fn):
        COMMANDS[name] = (fn, help_)
        return fn
    return deco


def _out(x):
    print(json.dumps(x, indent=1, default=str) if not isinstance(x, str) else x)


@command("/plan", "show the plan the agent would follow for a task")
def _plan(st, arg):
    _out(st["agent"].backend.plan_text(arg) if not getattr(st["agent"].backend, "can_plan", False) else "(external backend plans on /run)")


@command("/run", "run the agent on a task")
def _run(st, arg):
    _out(st["agent"].run(arg, st.get("workspace", ".")))


@command("/review", "review the working-tree diff (critique for HTML, tests for code)")
def _review(st, arg):
    from xon.agent.tools import Context, registry
    ctx = Context(st["root"], st["cfg"])
    t = registry()
    d = t["git"].run(ctx, "diff")
    files = [l[6:] for l in d.get("stdout", "").splitlines() if l.startswith("+++ b/")]
    out = {"changed": files, "tests": t["test"].run(ctx)["ok"]}
    for f in files:
        if f.endswith(".html"):
            out[f] = t["design"].run(ctx, "critique", path=f).get("score")
    _out(out)


@command("/test", "run tests")
def _test(st, arg):
    from xon.agent.tools import Context, registry
    r = registry()["test"].run(Context(st["root"], st["cfg"]), target=arg)
    _out({k: r[k] for k in ("ok", "passed", "failed", "cmd")})


@command("/diff", "show git diff")
def _diff(st, arg):
    from xon.agent.tools import Context, registry
    _out(registry()["git"].run(Context(st["root"], st["cfg"]), "diff").get("stdout", ""))


@command("/undo", "undo the last XON checkpoint commit")
def _undo(st, arg):
    from xon.agent.tools import Context, registry
    _out(registry()["git"].run(Context(st["root"], st["cfg"]), "undo"))


@command("/agents", "list parallel agents")
def _agents(st, arg):
    from xon.agent import manager
    _out([{k: a[k] for k in ("id", "state", "task")} for a in manager.agents(st["root"])])


@command("/spawn", "run a task in an isolated worktree (background)")
def _spawn(st, arg):
    from xon.agent import manager
    _out(manager.spawn(st["root"], arg))


@command("/crawl", "crawl once (mock unless --live)")
def _crawl(st, arg):
    from xon.nodes.crawler_node import crawl_once
    _out(crawl_once(st["cfg"], mock="--live" not in arg))


@command("/train", "run one learning cycle")
def _train(st, arg):
    from xon.trainer.cycle import Cycle
    r = Cycle(st["cfg"], quick="--quick" in arg).run()
    _out({k: r[k] for k in ("cycle", "promoted", "reason", "metrics")})


@command("/design", "design <prompt> -> index.html + screenshot + critique")
def _design(st, arg):
    _out(st["agent"].run(f"design {arg}", st.get("workspace", ".")))


@command("/status", "governor, nodes, last cycle")
def _status(st, arg):
    from xon.workstation.dashboard.server import gather
    d = gather(st["cfg"])
    _out({"governor": d["governor"], "nodes": d["nodes"], "cycles": len(d["history"]), "promoted": d["promoted"]})


def dispatch(st: dict, line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    if line in ("/quit", "/exit"):
        return False
    if line == "/help":
        for k, (_, h) in COMMANDS.items():
            print(f"{k:9s} {h}")
        return True
    name, _, arg = line.partition(" ")
    if name in COMMANDS:
        COMMANDS[name][0](st, arg)
    else:
        COMMANDS["/run"][0](st, line)
    return True
