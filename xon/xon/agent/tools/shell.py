from xon.agent.sandbox import run_shell

SPEC = {"name": "shell", "description": "Run a shell command in the project dir (sandboxed, timeout).",
        "params": {"cmd": "str", "timeout": "int?"}}


def run(ctx, cmd: str, timeout: int | None = None) -> dict:
    r = run_shell(cmd, ctx.root, timeout=timeout or ctx.cfg["agent"]["shell_timeout_s"])
    r["ok"] = r["code"] == 0
    return r
