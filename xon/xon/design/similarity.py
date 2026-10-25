"""Perceptual similarity between a render and a target: SSIM (structure) + color + edges -> 0..1."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

SIZE = (160, 120)


def _gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L").resize(SIZE, Image.BILINEAR), dtype=np.float64)


def ssim(a: Image.Image, b: Image.Image, win: int = 8) -> float:
    x, y = _gray(a), _gray(b)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    h, w = x.shape
    vals = []
    for i in range(0, h - win + 1, win // 2):
        for j in range(0, w - win + 1, win // 2):
            px, py = x[i:i + win, j:j + win], y[i:i + win, j:j + win]
            mx, my = px.mean(), py.mean()
            vx, vy = px.var(), py.var()
            cxy = ((px - mx) * (py - my)).mean()
            vals.append(((2 * mx * my + C1) * (2 * cxy + C2)) / ((mx ** 2 + my ** 2 + C1) * (vx + vy + C2)))
    return float(np.mean(vals))


def color_sim(a: Image.Image, b: Image.Image) -> float:
    x = np.asarray(a.convert("RGB").resize((40, 30), Image.BILINEAR), dtype=np.float64)
    y = np.asarray(b.convert("RGB").resize((40, 30), Image.BILINEAR), dtype=np.float64)
    d = np.sqrt(((x - y) ** 2).sum(-1)).mean() / (255 * np.sqrt(3))
    return float(1 - d)


def edge_sim(a: Image.Image, b: Image.Image) -> float:
    ea = np.asarray(a.convert("L").resize(SIZE).filter(ImageFilter.FIND_EDGES), dtype=np.float64) > 40
    eb = np.asarray(b.convert("L").resize(SIZE).filter(ImageFilter.FIND_EDGES), dtype=np.float64) > 40
    # tolerant overlap: dilate both by 1 px
    def dil(m):
        o = m.copy()
        o[1:] |= m[:-1]; o[:-1] |= m[1:]; o[:, 1:] |= m[:, :-1]; o[:, :-1] |= m[:, 1:]
        return o
    inter = (ea & dil(eb)).sum() + (eb & dil(ea)).sum()
    tot = ea.sum() + eb.sum()
    return float(inter / tot) if tot else 1.0


def fidelity(render: Image.Image, target: Image.Image) -> float:
    """Weighted perceptual similarity in [0,1]; 1 = identical."""
    s = (ssim(render, target) + 1) / 2
    return round(0.4 * s + 0.35 * color_sim(render, target) + 0.25 * edge_sim(render, target), 4)


def diff_image(a: Image.Image, b: Image.Image) -> Image.Image:
    x = np.asarray(a.convert("RGB").resize(b.size), dtype=np.int16)
    y = np.asarray(b.convert("RGB"), dtype=np.int16)
    d = np.abs(x - y).sum(-1).clip(0, 255).astype(np.uint8)
    return Image.fromarray(255 - d).convert("RGB")
