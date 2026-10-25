"""Sandboxed execution: project-dir jail, timeouts, resource limits, destructive-command denylist."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

DENY = [
    r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME|\*|\.\.)", r"\brm\s+-rf\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{",
    r"\bshutdown\b", r"\breboot\b", r"\bchmod\s+-R\s+777\s+/", r"\bcurl\b[^|]*\|\s*(ba)?sh", r"\bwget\b[^|]*\|\s*(ba)?sh",
    r"\bgit\s+push\s+.*--force", r"\bgit\s+reset\s+--hard\s+origin", r">\s*/dev/sd", r"\bsudo\b", r"\bkill\s+-9\s+1\b",
    r"\bcat\s+[^|]*(\.env|id_rsa|\.ssh/|credentials|\.netrc|\.aws/)", r"\bprintenv\b", r"\benv\b\s*$",
]
SECRET_PATHS = re.compile(r"(^|/)(\.env[^/]*|id_rsa[^/]*|\.ssh|\.aws|\.netrc|credentials[^/]*|.*\.pem|.*\.key)$")


class Denied(PermissionError):
    pass


def check_command(cmd: str) -> None:
    for pat in DENY:
        if re.search(pat, cmd):
            raise Denied(f"command blocked by XON denylist ({pat})")


def jail(root: Path, p: str | Path) -> Path:
    """Resolve p inside root or raise. Blocks secret files."""
    root = Path(root).resolve()
    q = (root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    if q != root and root not in q.parents:
        raise Denied(f"path {p} escapes project dir {root}")
    if SECRET_PATHS.search(str(q.relative_to(root)) if q != root else ""):
        raise Denied(f"refusing to touch secret-looking file {p}")
    return q


def _limits(mem_mb: int):
    def f():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
            os.setsid()
        except Exception:
            pass
    return f


def clean_env() -> dict:
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH", "TMPDIR", "SYSTEMROOT", "XON_HOME", "XON_CHROMIUM")
    return {k: v for k, v in os.environ.items() if k in keep or k.startswith("XON_")}


def run_shell(cmd: str, cwd: Path, timeout: float = 120, mem_mb: int = 4096) -> dict:
    check_command(cmd)
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=clean_env(), preexec_fn=_limits(mem_mb) if os.name == "posix" else None)
        return {"code": p.returncode, "stdout": p.stdout[-20000:], "stderr": p.stderr[-20000:]}
    except subprocess.TimeoutExpired as e:
        return {"code": 124, "stdout": (e.stdout or b"")[-5000:].decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                "stderr": f"timeout after {timeout}s"}


def run_python(source: str, timeout: float = 10, mem_mb: int = 1024) -> dict:
    """Run untrusted Python (e.g. model output + hidden tests) isolated in a temp dir."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "prog.py"
        f.write_text(source)
        try:
            p = subprocess.run([sys.executable, "-I", str(f)], cwd=d, capture_output=True, text=True, timeout=timeout,
                               env={"PATH": os.environ.get("PATH", "")},
                               preexec_fn=_limits(mem_mb) if os.name == "posix" else None)
            return {"ok": p.returncode == 0, "code": p.returncode, "stderr": p.stderr[-4000:], "stdout": p.stdout[-2000:]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "code": 124, "stderr": "timeout", "stdout": ""}


def run_tests_on(code: str, tests: list[str], timeout: float = 10) -> dict:
    prog = code + "\n\n" + "\n".join(f"assert {t}, {t!r}" for t in tests) + "\n"
    return run_python(prog, timeout=timeout)
