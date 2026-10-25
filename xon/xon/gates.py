"""Milestone gates M0-M4. Each is an automated check; results are written to exchange/gates.json."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from xon import config


def _record(cfg: dict, name: str, res: dict) -> dict:
    p = config.path(cfg, "exchange") / "gates.json"
    cur = json.loads(p.read_text()) if p.exists() else {}
    cur[name] = {**res, "t": time.time()}
    p.write_text(json.dumps(cur, indent=1, default=str))
    return res


def _history(cfg):
    p = config.path(cfg, "checkpoints") / "history.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def m0(cfg: dict, quick: bool = False) -> dict:
    """Tier A end to end < 30 min in a FRESH home: crawl (mock web), clean, open data (offline stdlib), train,
    evaluate, promote, dashboard."""
    root = Path(cfg["_root"])
    home = root / ".xon" / "gate-m0"
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    (home / "evalsets").symlink_to(root / "evalsets")
    shutil.copy(root / "xon.toml", home / "xon.toml") if (root / "xon.toml").exists() else None
    env = {**os.environ, "XON_HOME": str(home)}
    for k in ("XON_CHECKPOINTS", "XON_DATA", "XON_EXCHANGE"):
        env.pop(k, None)
    t0 = time.time()
    steps = [["crawl", "--mock"], ["train"] + (["--quick"] if quick else [])]
    logs = []
    for s in steps:
        p = subprocess.run([sys.executable, "-m", "xon.agent.cli", *s], env=env, cwd=home, capture_output=True, text=True)
        logs.append({"cmd": s, "code": p.returncode, "tail": (p.stdout + p.stderr)[-1500:]})
        if p.returncode != 0:
            return {"pass": False, "failed_step": s, "logs": logs}
    minutes = (time.time() - t0) / 60
    hcfg = config.load(home)
    hist = _history(hcfg)
    promoted = (config.path(hcfg, "checkpoints") / "promoted" / "lm.pt").exists()
    from xon.workstation.dashboard.server import serve
    srv = serve(hcfg, port=0, background=True)
    import urllib.request
    st = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/status", timeout=10).read())
    srv.shutdown()
    m = hist[-1]["metrics"] if hist else {}
    finite = all(isinstance(v, (int, float)) and math.isfinite(v) for v in m.values())
    ok = bool(hist) and promoted and finite and st["history"] and minutes < 30
    return {"pass": ok, "minutes": round(minutes, 2), "promoted": promoted, "metrics": m, "dashboard_ok": bool(st["history"]),
            "quick": quick, "home": str(home)}


def m1(cfg: dict, quick: bool = False) -> dict:
    """Real-data smoke: LM loss clearly falls, vision beats random by a stated margin, synthetic pairs stored right."""
    logs = config.path(cfg, "logs")
    tr = [r for r in config.jsonl_read(logs / "lm_train.jsonl") if "loss" in r]
    if not tr:
        return {"pass": False, "reason": "no LM training log; run `xon train`"}
    first = sum(r["loss"] for r in tr[:3]) / min(3, len(tr))
    last = sum(r["loss"] for r in tr[-3:]) / min(3, len(tr))
    hist = _history(cfg)
    m = hist[-1]["metrics"]
    margin = m["recog_top1"] - 0.1
    synth = sorted((config.path(cfg, "data") / "synth").glob("cycle-*"))
    from xon.datasets import synth_ui
    rows = synth_ui.load_index(synth[-1]) if synth else []
    imgs_ok = all((synth[-1] / r["image"]).exists() for r in rows) if rows else False
    boxes_ok = sum(1 for r in rows if r["boxes"]) / max(len(rows), 1)
    html_ok = all(r["html"].startswith("<!DOCTYPE html>") for r in rows)
    res = {"lm_loss_first": round(first, 3), "lm_loss_last": round(last, 3), "loss_drop": round(1 - last / first, 3),
           "recog_top1": m["recog_top1"], "chance": 0.1, "margin_over_chance": round(margin, 3), "ui_f1": m["ui_f1"],
           "synthetic_pairs": len(rows), "synthetic_images_present": imgs_ok, "synthetic_with_labels": round(boxes_ok, 3),
           "synthetic_html_ok": html_ok}
    res["pass"] = res["loss_drop"] > 0.3 and margin > 0.3 and imgs_ok and boxes_ok > 0.95 and html_ok
    return res


def m2(cfg: dict, quick: bool = False) -> dict:
    """Tier B stability check. Full M2 = hours on a GPU; here: Tier-B-shaped model, short run, recovery armed."""
    import numpy as np
    from xon.lm.model import shape_for_params
    from xon.lm.train import train
    from xon.workstation.budget import device
    dev = device()
    n = 1.0e8 if dev == "cuda" else 1.0e8
    c = shape_for_params(int(n), 4096, 256 if dev != "cuda" else 1024)
    steps = 12 if (quick or dev == "cpu") else 2000
    rng = np.random.default_rng(0)
    ids = np.tile(np.arange(64), 20000).astype(np.int32)
    ids = np.where(rng.random(len(ids)) < 0.05, rng.integers(0, 4096, len(ids)), ids).astype(np.int32)
    out = config.path(cfg, "checkpoints") / "gate-m2"
    shutil.rmtree(out, ignore_errors=True)
    t0 = time.time()
    r = train(c, ids, ids[:5000], out, max_steps=steps, batch=2 if dev == "cpu" else 16, lr=3e-4, warmup=2,
              eval_every=steps, inject={"nan_at": steps // 2})
    log = [json.loads(l) for l in (out / "train_log.jsonl").read_text().splitlines() if '"loss"' in l]
    shutil.rmtree(out, ignore_errors=True)
    stable = math.isfinite(r["val_loss"]) and any(e["event"] == "nan_rollback" for e in r["events"])
    return {"pass": stable, "device": dev, "params": c.n_params(), "steps": r["step"], "minutes": round((time.time() - t0) / 60, 2),
            "val_loss": r["val_loss"], "events": r["events"], "first_loss": log[0]["loss"] if log else None,
            "note": "hours-long Tier B run NOT executed (no GPU in this environment); this is the stability smoke check"
            if dev != "cuda" else ""}


def m3(cfg: dict, quick: bool = True) -> dict:
    """Crawler and trainer as separate OS processes sharing only a folder."""
    root = Path(cfg["_root"])
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "slow",
                        "tests/test_transport.py::test_m3_crawler_and_trainer_processes_share_a_folder"],
                       cwd=root, capture_output=True, text=True)
    return {"pass": p.returncode == 0, "output": p.stdout[-800:]}


def m4(cfg: dict, quick: bool = False) -> dict:
    """Agent: build an app from a prompt (test, design, screenshot, critique, improve) and fix a seeded bug in XON's
    own pipeline on a branch, merged only if tests pass and the gate shows no regression."""
    root = Path(cfg["_root"])
    work = root / ".xon" / "gate-m4"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = {**os.environ, "XON_CHECKPOINTS": str(config.path(cfg, "checkpoints")), "PYTHONPATH": ""}
    # --- part 1: build an app
    app = work / "app-project"
    app.mkdir()
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "xon@example.org"], ["git", "config", "user.name", "XON"]):
        subprocess.run(c, cwd=app, check=True)
    (app / "README.md").write_text("XON M4 demo project\n")
    subprocess.run(["git", "add", "-A"], cwd=app)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=app)
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "xon.agent.cli", "agent", "build a todo app called Errands with a teal theme",
                        "--mode", "full-auto", "--workspace", "errands", "--root", str(app)], cwd=app, capture_output=True,
                       text=True, env={**env, "XON_HOME": str(app)})
    summ = sorted((app / "artifacts").glob("*/summary.json"))
    s1 = json.loads(summ[-1].read_text()) if summ else {}
    part1 = bool(s1.get("tests_after")) and s1.get("critique_after", 0) >= s1.get("critique_before", 101) and \
        all(Path(x).exists() for x in s1.get("screenshots", []) if x)
    # --- part 2: seeded bug in XON's own pipeline, fixed by an agent on a branch in a clone
    xroot = work / "xon-clone"
    xroot.mkdir()
    for sub in ("xon", "tests", "evalsets"):
        shutil.copytree(root / sub, xroot / sub, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("pyproject.toml", "xon.toml", "XON.md"):
        if (root / f).exists():
            shutil.copy(root / f, xroot / f)
    (xroot / ".gitignore").write_text(".xon/\nartifacts/\nexchange/\ndata/\ncheckpoints/\nlogs/\n__pycache__/\n")
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "xon@example.org"], ["git", "config", "user.name", "XON"],
              ["git", "add", "-A"], ["git", "commit", "-qm", "XON snapshot for M4 gate"]):
        subprocess.run(c, cwd=xroot, check=True)
    target = xroot / "xon" / "pipeline" / "clean_code.py"
    src = target.read_text()
    seeded = src.replace('    if len(code) < 40:\n        return "too_short"', '    if len(code) > 40:\n        return "too_short"')
    assert seeded != src, "seed site not found"
    target.write_text(seeded)
    subprocess.run(["git", "commit", "-qam", "seeded bug (M4 gate)"], cwd=xroot)
    xenv = {**env, "XON_HOME": str(xroot), "PYTHONPATH": str(xroot)}
    before = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_pipeline.py"],
                            cwd=xroot, capture_output=True, text=True, env=xenv)
    from xon.agent import manager
    old = dict(os.environ)
    try:
        os.environ.update(xenv)
        meta = manager.spawn(xroot, "fix the failing tests in tests/test_pipeline.py", mode="auto-edit", wait=True,
                             extra=["--yes"])
    finally:
        os.environ.clear()
        os.environ.update(old)
    wt = Path(meta["worktree"])
    fixed_src = (wt / "xon" / "pipeline" / "clean_code.py").read_text()
    seed_line = "if len(code) > 40:"
    # self-improvement gate: tests + no regression on a pipeline metric (mock-crawl processing stats) vs. pre-bug code
    gate_tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_pipeline.py",
                                 "tests/test_crawler.py"], cwd=wt, capture_output=True, text=True, env={**xenv, "PYTHONPATH": str(wt)})
    probe = ("import json,tempfile,os; from pathlib import Path; d=tempfile.mkdtemp(); os.environ['XON_HOME']=d; "
             "os.symlink(os.path.abspath('evalsets'), Path(d)/'evalsets'); from xon import config; "
             "from xon.nodes.crawler_node import crawl_once; s=crawl_once(config.load(Path(d)), mock=True, open_data=False); "
             "print(json.dumps({k:v for k,v in s['clean'].items() if k in ('text','code','css','svg','image')}))")
    def metric(cwd):
        r = subprocess.run([sys.executable, "-c", probe], cwd=cwd, capture_output=True, text=True, env={**xenv, "PYTHONPATH": str(cwd)})
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return {"error": r.stderr[-500:]}
    m_branch, m_main = metric(wt), metric(root)
    no_regression = all(m_branch.get(k, 0) >= v for k, v in m_main.items() if isinstance(v, int))
    merged = []
    if gate_tests.returncode == 0 and no_regression:
        merged = manager.collect(xroot, [meta["id"]], require_tests=False)
    part2 = (before.returncode != 0 and gate_tests.returncode == 0 and no_regression and bool(merged and merged[0]["merged"])
             and seed_line not in fixed_src)
    agent_summary = sorted((wt / "artifacts").glob("*/summary.json"))
    s2 = json.loads(agent_summary[-1].read_text()) if agent_summary else {}
    return {"pass": bool(part1 and part2), "minutes": round((time.time() - t0) / 60, 2),
            "build_app": {"ok": part1, **{k: s1.get(k) for k in ("tests_before", "tests_after", "critique_before", "critique_after",
                                                                 "issues_before", "issues_after", "fixes", "screenshots", "artifacts")}},
            "self_fix": {"ok": part2, "tests_failed_before": before.returncode != 0, "agent": {k: s2.get(k) for k in ("fixed", "file", "tries", "diff")},
                         "tests_after_on_branch": gate_tests.returncode == 0, "metric_main": m_main, "metric_branch": m_branch,
                         "merged": merged, "app_project": str(app)}}


def run(name: str, cfg: dict, quick: bool = False) -> dict:
    res = {"m0": m0, "m1": m1, "m2": m2, "m3": m3, "m4": m4}[name](cfg, quick=quick)
    return _record(cfg, name, res)
