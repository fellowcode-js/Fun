from xon.agent.sandbox import run_python

SPEC = {"name": "python_run", "description": "Run a Python snippet in the sandbox (isolated temp dir, timeout, memory cap).",
        "params": {"code": "str", "timeout": "int?"}}


def run(ctx, code: str, timeout: int = 20) -> dict:
    r = run_python(code, timeout=timeout)
    return {"ok": r["ok"], "code": r["code"], "stdout": r["stdout"], "stderr": r["stderr"]}
