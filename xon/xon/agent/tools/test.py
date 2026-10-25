"""Test runner with auto-detection: pytest, npm test, or unittest."""
import json
import re
import shutil
import sys
from pathlib import Path

from xon.agent.sandbox import run_shell

SPEC = {"name": "test", "description": "Run the project's tests (auto-detects pytest / npm / unittest).",
        "params": {"target": "str?", "cmd": "str?"}}


def detect(root: Path) -> str:
    if (root / "package.json").exists() and shutil.which("npm"):
        try:
            if "test" in json.loads((root / "package.json").read_text()).get("scripts", {}):
                return "npm test --silent"
        except Exception:
            pass
    found = list(root.glob("**/test_*.py")) + list(root.glob("**/*_test.py"))
    if any(".xon" not in p.relative_to(root).parts for p in found) or (root / "pytest.ini").exists():
        return f"{sys.executable} -m pytest -q -x -p no:cacheprovider"
    return f"{sys.executable} -m unittest discover -q"


def parse(out: str) -> dict:
    m = re.search(r"(\d+) failed", out)
    p = re.search(r"(\d+) passed", out)
    return {"failed": int(m.group(1)) if m else 0, "passed": int(p.group(1)) if p else 0}


def run(ctx, target: str = "", cmd: str = "") -> dict:
    cmd = cmd or detect(ctx.root)
    if target:
        cmd = f"{cmd} {target}"
    r = run_shell(cmd, ctx.root, timeout=ctx.cfg["agent"].get("test_timeout_s", 600))
    out = r["stdout"] + r["stderr"]
    return {"ok": r["code"] == 0, "cmd": cmd, "code": r["code"], **parse(out), "output": out[-6000:]}
