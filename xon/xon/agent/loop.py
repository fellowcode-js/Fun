"""Agent loop: task -> plan.md -> tool calls -> run tests -> verify -> summary with diff.
Stops on done, step limit, three identical failures, or interrupt. Every tool call is logged."""
from __future__ import annotations

import json
import time
from pathlib import Path

from xon import config
from xon.agent import hooks, memory, verify
from xon.agent.artifacts import Artifacts, task_id
from xon.agent.backends import pick
from xon.agent.permissions import PermissionDenied, Permissions
from xon.agent.sandbox import Denied
from xon.agent.tools import Context, registry, schemas

SYSTEM = """You are the XON agent, a coding and design assistant working inside a project directory.
Use the tools to inspect, edit, test and verify. Keep changes minimal. For UI work, screenshot and critique.
When done, reply with a short summary and no tool calls."""


class Agent:
    def __init__(self, root: Path, cfg: dict | None = None, mode: str | None = None, backend: str | None = None,
                 assume_yes: bool = False, allow_protected: bool = False, max_steps: int | None = None):
        self.root = Path(root).resolve()
        self.cfg = cfg or config.load(self.root)
        a = self.cfg["agent"]
        self.perms = Permissions(mode or a["permission_mode"], allow_protected=allow_protected,
                                 allowlist=a.get("tool_allowlist") or None, assume_yes=assume_yes)
        self.backend = pick(backend or a["backend"])
        self.tools = registry()
        self.max_steps = max_steps or a["max_steps"]
        self.hooks = a.get("hooks", {})

    def call(self, ctx: Context, art: Artifacts, name: str, args: dict) -> dict:
        t0 = time.time()
        try:
            if name == "_screenshot":
                res = verify.screenshot(self.root, args["path"], art.screenshot_path(args["name"]), args.get("interact", False), ctx.vision())
            elif name == "_improve":
                self.perms.check("edit", {"path": args["path"]})
                res = verify.improve(self.root, args["path"], args["report"])
            else:
                self.perms.check(name, args)
                hooks.run_hooks(self.hooks.get("pre_tool", []), name, args, None, self.root, "pre")
                res = self.tools[name].run(ctx, **args)
                hooks.run_hooks(self.hooks.get("post_tool", []), name, args, res, self.root, "post")
        except (PermissionDenied, Denied, hooks.HookBlocked) as e:
            res = {"ok": False, "error": str(e), "denied": True}
        except Exception as e:  # tool bug: report, don't crash the loop
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        art.log({"tool": name, "args": {k: (v if not isinstance(v, (str, dict)) or len(str(v)) < 400 else str(v)[:400] + "...")
                                        for k, v in args.items()},
                 "ok": res.get("ok"), "error": res.get("error"), "ms": int((time.time() - t0) * 1000)})
        return res

    def run(self, task: str, workspace: str = ".") -> dict:
        tid = task_id(task)
        art = Artifacts(self.root, tid)
        ctx = Context(self.root, self.cfg, art)
        art.status(task=task, state="running", backend=self.backend.name, started=time.time())
        mem = memory.load(self.root)
        base = self._git("rev-parse HEAD")
        failures: list[str] = []
        steps = 0
        summary: dict = {}
        try:
            if getattr(self.backend, "can_plan", False):
                summary = self._llm_loop(task, ctx, art, mem, failures)
                steps = summary.pop("_steps", 0)
            else:
                art.write("plan.md", self.backend.plan_text(task))
                gen = self.backend.recipe(task, workspace)
                res = None
                while True:
                    try:
                        name, args = gen.send(res) if res is not None else next(gen)
                    except StopIteration as stop:
                        summary = stop.value or {}
                        break
                    steps += 1
                    if steps > self.max_steps:
                        summary = {"stopped": "step limit"}
                        break
                    res = self.call(ctx, art, name, args)
                    if not res.get("ok", True):
                        failures.append(f"{name}:{res.get('error')}")
                        if len(failures) >= 3 and len(set(failures[-3:])) == 1:
                            summary = {"stopped": "three identical failures", "error": failures[-1]}
                            break
        except KeyboardInterrupt:
            summary = {"stopped": "interrupted"}
        diff = self._git(f"diff {base.strip()} HEAD") if base.strip() else ""
        diff += self._git("diff")
        art.write("diff.patch", diff)
        summary.update({"task": task, "task_id": tid, "steps": steps, "backend": self.backend.name,
                        "artifacts": str(art.dir.relative_to(self.root))})
        art.write("summary.json", json.dumps(summary, indent=1, default=str))
        art.status(state="done", finished=time.time(), summary={k: v for k, v in summary.items() if k != "diff"})
        return summary

    def _git(self, args: str) -> str:
        from xon.agent.sandbox import run_shell
        r = run_shell(f"git {args}", self.root, timeout=60)
        return r["stdout"] if r["code"] == 0 else ""

    def _llm_loop(self, task, ctx, art, mem, failures) -> dict:
        msgs = [{"role": "system", "content": SYSTEM + ("\n\nProject memory (XON.md):\n" + mem[:6000] if mem else "")},
                {"role": "user", "content": f"Task: {task}\nFirst write a short numbered plan, then use tools."}]
        specs = schemas()
        steps = 0
        last = ""
        while steps < self.max_steps:
            resp = self.backend.chat(msgs, specs)
            if steps == 0 and resp["content"]:
                art.write("plan.md", resp["content"])
            if not resp["tool_calls"]:
                last = resp["content"]
                break
            results = []
            for c in resp["tool_calls"]:
                steps += 1
                r = self.call(ctx, art, c["name"], c["args"])
                results.append((c, r))
                if not r.get("ok", True):
                    failures.append(f"{c['name']}:{r.get('error')}")
                    if len(failures) >= 3 and len(set(failures[-3:])) == 1:
                        return {"stopped": "three identical failures", "_steps": steps}
            msgs += self.backend.tool_result_messages(resp, results)
        t = self.tools["test"].run(ctx)
        return {"summary": last, "tests_ok": t["ok"], "_steps": steps}
