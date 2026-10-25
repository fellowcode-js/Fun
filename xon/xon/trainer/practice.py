"""Practice round (rejection sampling): the warm-start coder solves training tasks; only solutions that pass the
task's own tests become training pairs. Never trains on unverified model output. Eval sets are never used here."""
from __future__ import annotations

import json
from pathlib import Path

from xon.agent.sandbox import run_python
from xon.pipeline.store import EvalGuard


def run(coder, tasks: list[dict], out: Path, evalsets: Path, limit: int = 120, samples: int = 2, log=None) -> dict:
    """tasks: instruct records with 'task', 'tests' (assert lines). Appends verified pairs to out (jsonl)."""
    out = Path(out)
    done = set()
    if out.exists():
        done = {json.loads(l)["task"] for l in out.read_text().splitlines() if l.strip()}
    guard = EvalGuard(evalsets)
    kept = tried = 0
    with open(out, "a") as f:
        for t in tasks:
            if tried >= limit:
                break
            if t["task"] in done or not t.get("tests"):
                continue
            tried += 1
            prompt = f"{t['task']}\nYour code should pass these tests:\n{t['tests']}"
            for attempt in range(samples):
                r = coder.write_code(prompt, "python")
                code = r["code"]
                if run_python(code + "\n\n" + t["tests"] + "\n", timeout=10)["ok"]:
                    rec = {"kind": "instruct", "task": t["task"], "tests": t["tests"], "code": code.strip(),
                           "license": "Apache-2.0-model-output; task CC-BY-4.0", "source": f"xon-practice:{coder.name}"}
                    if not guard.collides(rec):
                        f.write(json.dumps(rec) + "\n")
                        kept += 1
                    break
            if log and tried % 10 == 0:
                log.info(f"practice: {kept}/{tried} verified")
    return {"tried": tried, "kept": kept, "file": str(out)}
