"""Manager view: parallel agents in isolated git worktrees. spawn -> agents -> collect (merge + conflicts)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from xon.agent.artifacts import task_id


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def spawn(root: Path, task: str, mode: str = "auto-edit", wait: bool = False, extra: list[str] | None = None) -> dict:
    root = Path(root).resolve()
    tid = task_id(task)
    branch = f"xon/{tid}"
    wt = root / ".xon" / "worktrees" / tid
    wt.parent.mkdir(parents=True, exist_ok=True)
    _git(root, "worktree", "add", "-q", "-b", branch, str(wt), "HEAD")
    meta = {"id": tid, "task": task, "branch": branch, "worktree": str(wt), "started": time.time(), "state": "running"}
    reg = root / ".xon" / "agents"
    reg.mkdir(parents=True, exist_ok=True)
    log = open(reg / f"{tid}.log", "w")
    cmd = [sys.executable, "-m", "xon.agent.cli", "agent", task, "--mode", mode, "--root", str(wt)] + (extra or [])
    p = subprocess.Popen(cmd, cwd=wt, stdout=log, stderr=subprocess.STDOUT, env=_env(root, wt))
    meta["pid"] = p.pid
    (reg / f"{tid}.json").write_text(json.dumps(meta, indent=1))
    if wait:
        p.wait()
        meta["state"] = "done" if p.returncode == 0 else "failed"
        meta["returncode"] = p.returncode
        (reg / f"{tid}.json").write_text(json.dumps(meta, indent=1))
    return meta


def _env(root: Path, wt: Path) -> dict:
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(wt)
    env["XON_HOME"] = str(wt)
    # share trained models with the main checkout so spawned agents can use them
    env["XON_CHECKPOINTS"] = str(root / "checkpoints")
    return env


def agents(root: Path) -> list[dict]:
    reg = Path(root) / ".xon" / "agents"
    out = []
    for f in sorted(reg.glob("*.json")) if reg.exists() else []:
        m = json.loads(f.read_text())
        if m["state"] == "running" and m.get("pid"):
            try:
                import os
                os.kill(m["pid"], 0)
            except OSError:
                st = Path(m["worktree"]) / "artifacts"
                m["state"] = "done" if st.exists() else "exited"
                f.write_text(json.dumps(m, indent=1))
        out.append(m)
    return out


def collect(root: Path, ids: list[str] | None = None, require_tests: bool = True) -> list[dict]:
    """Merge finished agent branches into the current branch. Conflicts are aborted and flagged."""
    root = Path(root).resolve()
    results = []
    for m in agents(root):
        if ids and m["id"] not in ids:
            continue
        if m["state"] not in ("done", "exited"):
            results.append({"id": m["id"], "merged": False, "reason": f"state={m['state']}"})
            continue
        wt = Path(m["worktree"])
        _git(wt, "add", "-A", check=False)
        _git(wt, "commit", "-q", "-m", f"xon agent {m['id']}: {m['task'][:60]}", check=False)
        if require_tests and (wt / "tests").exists():
            t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests", "-m", "not slow and not browser"],
                               cwd=wt, capture_output=True, text=True, env=_env(root, wt))
            if t.returncode != 0:
                results.append({"id": m["id"], "merged": False, "reason": "tests fail on agent branch", "output": t.stdout[-1500:]})
                continue
        r = _git(root, "merge", "--no-ff", "-q", "-m", f"xon collect {m['id']}", m["branch"], check=False)
        if r.returncode != 0:
            files = _git(root, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            _git(root, "merge", "--abort", check=False)
            results.append({"id": m["id"], "merged": False, "reason": "conflict", "conflicts": files})
            continue
        m["state"] = "collected"
        (root / ".xon" / "agents" / f"{m['id']}.json").write_text(json.dumps(m, indent=1))
        results.append({"id": m["id"], "merged": True})
    return results
