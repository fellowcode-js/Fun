"""Inference helpers: classify / zero-shot / detect UI elements / pseudo-label."""
from __future__ import annotations

import torch
from PIL import Image

from xon.datasets.shapes import SHAPES
from xon.pipeline.label import pseudo_label
from xon.vision.train import to_tensor
from xon.vision.ui_detect import DET_H, DET_W, decode


@torch.no_grad()
def classify(model, img: Image.Image, topk: int = 5) -> list[tuple[str, float]]:
    p = torch.softmax(model.classify(to_tensor(img, (64, 64))[None]), -1)[0]
    v, i = p.topk(min(topk, len(SHAPES)))
    return [(SHAPES[j], round(float(s), 4)) for s, j in zip(v, i)]


@torch.no_grad()
def zero_shot(model, img: Image.Image, names: list[str] = SHAPES) -> list[tuple[str, float]]:
    s = model.zero_shot(to_tensor(img, (64, 64))[None], names)[0]
    p = torch.softmax(s * 30, -1)
    return sorted(zip(names, [round(float(x), 4) for x in p]), key=lambda t: -t[1])


@torch.no_grad()
def detect(model, img: Image.Image, thresh: float = 0.35) -> list[dict]:
    out = model.detect_raw(to_tensor(img, (DET_W, DET_H))[None])[0]
    return decode(out, img.size[0], img.size[1], thresh=thresh)


@torch.no_grad()
def pseudo_labels(model, images: list[Image.Image], threshold: float = 0.8) -> list[dict | None]:
    if not images:
        return []
    x = torch.stack([to_tensor(i, (64, 64)) for i in images])
    p = torch.softmax(model.classify(x), -1)
    return [pseudo_label(row.tolist(), SHAPES, threshold) for row in p]
