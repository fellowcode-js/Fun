"""Vision evals on FROZEN sets: recognition top-1/top-5 + zero-shot; UI detection P/R/F1 @ IoU 0.5."""
from __future__ import annotations

import json
from pathlib import Path

import torch

from xon.datasets import shapes, synth_ui
from xon.vision import predict
from xon.vision.train import to_tensor
from xon.vision.ui_detect import match


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


@torch.no_grad()
def recognition(model, evalsets: Path) -> dict:
    seeds = [r["seed"] for r in load(Path(evalsets) / "recognition_heldout.jsonl")]
    imgs, ys = [], []
    for s in seeds:
        img, shape, _, _ = shapes.make(s)
        imgs.append(to_tensor(img, (64, 64)))
        ys.append(shapes.SHAPES.index(shape))
    x, y = torch.stack(imgs), torch.tensor(ys)
    logits = model.classify(x)
    top5 = logits.topk(5, -1).indices
    zs = model.zero_shot(x, shapes.SHAPES).argmax(-1)
    return {"n": len(seeds), "classes": len(shapes.SHAPES), "chance_top1": round(1 / len(shapes.SHAPES), 4),
            "top1": round(float((top5[:, 0] == y).float().mean()), 4),
            "top5": round(float((top5 == y[:, None]).any(-1).float().mean()), 4),
            "zero_shot_top1": round(float((zs == y).float().mean()), 4)}


def ui_heldout(evalsets: Path, cache: Path, renderer=None, version: int = 1) -> list[dict]:
    """Render (once, cached) the frozen held-out UI seeds for a generator version."""
    cache = Path(cache) if version == 1 else Path(str(cache) + f"_v{version}")
    rows = synth_ui.load_index(cache)
    fname = "ui_heldout.jsonl" if version == 1 else f"ui_heldout_v{version}.jsonl"
    seeds = [r["seed"] for r in load(Path(evalsets) / fname)]
    if len(rows) >= len(seeds):
        return rows
    if cache.exists():
        for f in cache.glob("*"):
            f.unlink()
    return synth_ui.generate(cache, len(seeds), start_seed=seeds[0], renderer=renderer, version=version)


def ui_detection(model, evalsets: Path, cache: Path, thresh: float = 0.35, renderer=None, version: int = 1) -> dict:
    from PIL import Image
    rows = ui_heldout(evalsets, cache, renderer, version)
    cache = Path(cache) if version == 1 else Path(str(cache) + f"_v{version}")
    tp = fp = fn = 0
    per = {}
    for r in rows:
        img = Image.open(Path(cache) / r["image"]).convert("RGB")
        preds = predict.detect(model, img, thresh)
        m = match(preds, r["boxes"])
        tp, fp, fn = tp + m["tp"], fp + m["fp"], fn + m["fn"]
        for c, v in m["per_class"].items():
            pc = per.setdefault(c, {"tp": 0, "fp": 0, "fn": 0})
            for k in v:
                pc[k] += v[k]
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    per_f1 = {c: round(2 * v["tp"] / max(2 * v["tp"] + v["fp"] + v["fn"], 1), 3) for c, v in per.items()}
    return {"images": len(rows), "precision": round(prec, 4), "recall": round(rec, 4), "f1@0.5": round(f1, 4),
            "per_class_f1": per_f1}
