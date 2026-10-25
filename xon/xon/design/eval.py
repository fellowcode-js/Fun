"""Design evals on FROZEN sets: screenshot->code fidelity, contrast-checker correctness, critique sanity."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from xon.design import palette
from xon.design.from_screenshot import from_screenshot


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def contrast_accuracy(evalsets: Path, tol: float = 0.02) -> dict:
    rows = load(Path(evalsets) / "contrast_cases.jsonl")
    ok = 0
    worst = 0.0
    for r in rows:
        got = palette.contrast(r["fg"], r["bg"])
        err = abs(got - r["ratio"])
        worst = max(worst, err)
        ok += err <= tol + 0.005 * r["ratio"]
    # pass/fail agreement at AA for the same cases
    agree = sum((palette.contrast(r["fg"], r["bg"]) >= 4.5) == (r["ratio"] >= 4.5) for r in rows)
    return {"cases": len(rows), "within_tolerance": ok, "accuracy": round(ok / len(rows), 4),
            "aa_agreement": round(agree / len(rows), 4), "max_abs_error": round(worst, 4)}


def fidelity_eval(vision_model, evalsets: Path, cache: Path, renderer, limit: int = 12, steps: int = 8) -> dict:
    from xon.vision.eval import ui_heldout
    rows = ui_heldout(evalsets, cache, renderer)[:limit]
    base, init, final = [], [], []
    for r in rows:
        img = Image.open(Path(cache) / r["image"]).convert("RGB")
        res = from_screenshot(img, vision_model, renderer, steps=steps)
        base.append(res["baseline_bg_only"])
        init.append(res["initial"])
        final.append(res["final"])
    return {"images": len(rows), "steps": steps, "fidelity_bg_only_baseline": round(float(np.mean(base)), 4),
            "fidelity_initial": round(float(np.mean(init)), 4), "fidelity_final": round(float(np.mean(final)), 4)}


def critique_sanity(renderer) -> dict:
    """Seeded defects must be found; a clean generated page should score high."""
    from xon.design import critique, from_prompt
    bad = ('<html><body style="background:#fff"><h2 style="font-size:30px">Big h2</h2><h1 style="font-size:16px">Small h1</h1>'
           '<button style="background:#ffeb3b;color:#ffffff;width:20px;height:18px">Go</button>'
           '<img src="x.png"><input placeholder=""></body></html>')
    rb = critique.critique_html(bad, renderer)
    found = {i["category"] for i in rb["issues"]}
    good = from_prompt.generate("a light landing page with three feature cards and a signup form with name and email")
    rg = critique.critique_html(good["html"], renderer)
    expected = {"contrast", "hierarchy", "accessibility"}
    return {"seeded_found": sorted(found & expected), "seeded_expected": sorted(expected),
            "recall": round(len(found & expected) / len(expected), 4), "bad_score": rb["score"],
            "generated_page_score": rg["score"], "generated_contrast_failed": rg["contrast_failed"]}
