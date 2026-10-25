"""Promotion gate: a candidate replaces the promoted checkpoint only if it beats it beyond a noise margin
on the primary metric and regresses no tracked metric past the allowed threshold."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

# metric -> direction (+1 higher is better, -1 lower is better)
METRICS = {
    "code_ppl": -1, "code_pass@1": +1, "code_pass@5": +1, "bugfix_rate": +1,
    "design_fidelity": +1, "ui_f1": +1, "recog_top1": +1, "recog_zero_shot": +1, "contrast_accuracy": +1,
}
PRIMARY = ["code_ppl", "ui_f1", "recog_top1", "design_fidelity"]


def rel_change(new: float, old: float, direction: int) -> float:
    """Positive = improvement, as a fraction of the old value."""
    if old == 0:
        return (new - old) * direction
    return (new - old) / abs(old) * direction


def decide(cand: dict, best: dict | None, noise_margin: float = 0.002, max_regression: float = 0.02) -> dict:
    if not best:
        return {"promote": True, "reason": "no promoted checkpoint yet"}
    deltas = {m: rel_change(cand[m], best[m], d) for m, d in METRICS.items() if m in cand and m in best}
    regress = {m: round(v, 4) for m, v in deltas.items() if v < -max_regression}
    if regress:
        return {"promote": False, "reason": f"regression beyond {max_regression:.0%}: {regress}", "deltas": deltas}
    gains = {m: round(deltas[m], 4) for m in PRIMARY if m in deltas and deltas[m] > noise_margin}
    if not gains:
        return {"promote": False, "reason": f"no primary metric improved beyond noise margin {noise_margin}", "deltas": deltas}
    return {"promote": True, "reason": f"improved {gains}", "deltas": deltas}


class Registry:
    """checkpoints/promoted/{lm,vision,tokenizer} + history.jsonl."""

    def __init__(self, ckpt_dir: Path):
        self.dir = Path(ckpt_dir)
        self.promoted = self.dir / "promoted"
        self.promoted.mkdir(parents=True, exist_ok=True)
        self.hist = self.dir / "history.jsonl"

    def best_metrics(self) -> dict | None:
        f = self.promoted / "metrics.json"
        return json.loads(f.read_text()) if f.exists() else None

    def promote(self, files: dict[str, Path], metrics: dict, cycle: int) -> None:
        stage = self.dir / f".stage-{int(time.time() * 1000)}"
        stage.mkdir()
        for name, src in files.items():
            if src and Path(src).exists():
                shutil.copy2(src, stage / name)
        (stage / "metrics.json").write_text(json.dumps({**metrics, "cycle": cycle, "t": time.time()}, indent=1))
        old = self.dir / ".old"
        if old.exists():
            shutil.rmtree(old)
        if self.promoted.exists():
            self.promoted.rename(old)
        stage.rename(self.promoted)
        shutil.rmtree(old, ignore_errors=True)

    def log(self, rec: dict) -> None:
        with open(self.hist, "a") as f:
            f.write(json.dumps({"t": time.time(), **rec}) + "\n")

    def history(self) -> list[dict]:
        if not self.hist.exists():
            return []
        return [json.loads(l) for l in self.hist.read_text().splitlines() if l.strip()]
