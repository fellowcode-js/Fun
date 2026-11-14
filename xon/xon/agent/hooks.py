"""Hooks from xon.toml: [agent.hooks] pre_tool / post_tool shell commands. A failing pre-hook blocks the tool."""
from __future__ import annotations

import json
import os
import subprocess


class HookBlocked(RuntimeError):
    pass


def run_hooks(cmds: list[str], tool: str, args: dict, result: dict | None, cwd, phase: str) -> None:
    for cmd in cmds or []:
        env = {**os.environ, "XON_TOOL": tool, "XON_ARGS": json.dumps(args)[:8000], "XON_PHASE": phase}
        if result is not None:
            env["XON_RESULT"] = json.dumps(result, default=str)[:8000]
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
        if phase == "pre" and p.returncode != 0:
            raise HookBlocked(f"pre_tool hook blocked {tool}: {p.stderr.strip() or p.stdout.strip()}")
