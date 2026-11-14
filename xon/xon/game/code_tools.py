"""The "code" toolkit: tools a coding sub-agent (reviewer, tester, helper) may be granted.
Everything runs in XON's sandbox (temp dir, timeout, memory cap)."""
from __future__ import annotations

from pathlib import Path

from xon.game import GameTool, Toolkit


def toolkit(root: Path | None = None) -> Toolkit:
    from xon import config
    from xon.agent.sandbox import run_cpp, run_python

    def python_run(code: str) -> dict:
        r = run_python(code, timeout=20)
        return {k: r.get(k) for k in ("ok", "code", "stdout", "stderr") if k in r}

    def cpp_run(code: str) -> dict:
        r = run_cpp(code, timeout=30)
        return {k: r.get(k) for k in ("ok", "stage", "code", "stdout", "stderr") if k in r}

    def write_code(task: str, lang: str = "python") -> dict:
        from xon.lm.pretrained import load
        pt = load(config.load(root) if root else config.load())
        if pt is None:
            return {"ok": False, "error": "local coder not installed (run scripts/setup.sh)"}
        r = pt.write_code(task, lang)
        code = r["code"]
        if lang != "python":
            test = run_cpp(code, timeout=30) if "main(" in code else {"ok": None}
        else:  # separate test block if the model wrote one; otherwise its own asserts/test calls inside the code
            runner = ("\n\nfor _n, _f in list(globals().items()):\n    if _n.startswith('test_') and callable(_f):\n"
                      "        _f()\nprint('tests passed')\n")
            test = run_python(code + "\n\n" + r["tests"] + runner if r["tests"] else code, timeout=20)
            if not r["tests"] and "assert" not in code and "test" not in code:
                test = {"ok": None, "stdout": test.get("stdout", ""), "stderr": test.get("stderr", "")}
        return {"ok": True, "code": code, "tests": r["tests"], "tests_passed": test.get("ok"),
                "test_output": (test.get("stdout", "") + test.get("stderr", ""))[-1500:]}

    return Toolkit("code", [
        GameTool("python_run", "Run a Python program in the sandbox; returns stdout/stderr.", {"code": "str"}, python_run),
        GameTool("cpp_run", "Compile and run a C++17 program in the sandbox.", {"code": "str"}, cpp_run),
        GameTool("write_code", "Write code + tests for a task with XON's local coder, then run the tests.",
                 {"task": "str", "lang": "str?"}, write_code),
    ])
