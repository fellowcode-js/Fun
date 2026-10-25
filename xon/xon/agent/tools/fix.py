"""fix: failing tests -> localized patch. Ochiai fault localization over pytest coverage, then search-based
repair on the most suspicious lines (LM-ranked when a local XON LM exists); every candidate is verified by
running the failing tests, then the whole suite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from xon.agent.faultloc import ochiai
from xon.agent.sandbox import run_shell
from xon.lm import repair

SPEC = {"name": "fix", "description": "Find and patch the bug that makes tests fail (localize + repair + verify).",
        "params": {"tests": "str?", "max_files": "int?"}}


def _pytest(ctx, args: str, env_extra: dict | None = None, timeout: int = 600) -> dict:
    env = " ".join(f"{k}={v}" for k, v in (env_extra or {}).items())
    return run_shell(f"{env} {sys.executable} -m pytest -q -p no:cacheprovider {args}".strip(), ctx.root, timeout=timeout)


def run(ctx, tests: str = "tests", max_files: int = 3, max_tries: int = 400) -> dict:
    out = Path(tempfile.mkdtemp()) / "faultloc.json"
    r = _pytest(ctx, f"-p xon.agent.faultloc {tests}", {"XON_FAULTLOC_OUT": str(out), "XON_FAULTLOC_ROOT": str(ctx.root),
                                                       "PYTHONPATH": str(ctx.root)})
    if r["code"] == 0:
        return {"ok": True, "note": "all tests pass; nothing to fix"}
    if not out.exists():
        return {"ok": False, "error": "could not collect coverage", "output": (r["stdout"] + r["stderr"])[-3000:]}
    data = json.loads(out.read_text())
    failing = [t for t, ok in data["res"].items() if not ok]
    ranked = ochiai(data)
    if not ranked:
        return {"ok": False, "error": "no suspicious source lines", "failing": failing}
    by_file: dict[str, list[int]] = {}
    for f, line, s in ranked[:40]:
        by_file.setdefault(f, []).append(line - 1)
    fail_sel = " ".join(f"'{t}'" for t in failing[:20])
    m, tok = ctx.lm()
    scorer = (lambda c: __import__("xon.lm.eval", fromlist=["lm_score"]).lm_score(m, tok, c[-2000:])) if m is not None else None
    tried = 0
    for f in list(by_file)[:max_files]:
        p = ctx.path(f)
        orig = p.read_text()

        def check(code: str) -> dict:
            p.write_text(code)
            rr = _pytest(ctx, f"-x {fail_sel}", {"PYTHONPATH": str(ctx.root)}, timeout=300)
            return {"ok": rr["code"] == 0, "stderr": rr["stdout"][-2000:]}

        cands = repair.mutants(orig, by_file[f][:12])
        if scorer:
            cands.sort(key=scorer)
        pt = ctx.pretrained()
        if pt is not None and f.endswith(".py"):
            cands = cands[:max_tries] + _llm_candidates(pt, orig, by_file[f][0], r["stdout"][-2000:])
        for c in cands[:max_tries + 4]:
            tried += 1
            if check(c)["ok"]:
                p.write_text(c)
                full = _pytest(ctx, tests, {"PYTHONPATH": str(ctx.root)})
                if full["code"] == 0:
                    diff = repair.unified_diff(orig, c, f)
                    return {"ok": True, "file": f, "diff": diff, "tries": tried, "failing_before": failing,
                            "suspicious": [(a, b, round(s, 3)) for a, b, s in ranked[:5]]}
                p.write_text(orig)  # fixed the failing tests but broke others: keep searching
        p.write_text(orig)
    return {"ok": False, "error": "no candidate patch passed", "tries": tried, "failing": failing,
            "suspicious": [(a, b, round(s, 3)) for a, b, s in ranked[:5]]}


def _llm_candidates(pt, src: str, line0: int, failure: str, n: int = 4) -> list[str]:
    """Rewrite only the function enclosing the most suspicious line; splice each proposal back into the file."""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno - 1 <= line0 <= (node.end_lineno or node.lineno) - 1:
            if fn is None or node.lineno > fn.lineno:
                fn = node
    if fn is None:
        return []
    lines = src.split("\n")
    a, b = fn.lineno - 1, fn.end_lineno
    func = "\n".join(lines[a:b])
    out = []
    for prop in pt.rewrite(func, failure, n=n):
        prop = prop.rstrip("\n")
        if f"def {fn.name}(" not in prop:
            continue
        out.append("\n".join(lines[:a] + prop.split("\n") + lines[b:]))
    return out
