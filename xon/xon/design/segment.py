"""Pixel segmentation of a UI screenshot into boxes (uniform fills) and text runs, for screenshot->code."""
from __future__ import annotations

import numpy as np
from PIL import Image


def _dominant(arr: np.ndarray) -> np.ndarray:
    px = arr.reshape(-1, 3)
    q = (px // 12).astype(np.int32)
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    k = vals[counts.argmax()]
    return px[keys == k].mean(0)


def components(mask: np.ndarray, min_px: int = 4) -> list[tuple[int, int, int, int, int]]:
    """4-connected components -> (x0, y0, x1, y1, n_pixels). Iterative flood fill (no scipy needed)."""
    H, W = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = True
        x0 = x1 = x
        y0 = y1 = y
        n = 0
        while stack:
            cy, cx = stack.pop()
            n += 1
            x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if n >= min_px:
            out.append((x0, y0, x1 + 1, y1 + 1, n))
    return out


def _merge_text(boxes: list[tuple], gap: int) -> list[list[int]]:
    """Merge glyph components on the same line into text runs."""
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    runs: list[list[int]] = []
    for x0, y0, x1, y1, _ in boxes:
        for r in runs:
            same_line = min(r[3], y1) - max(r[1], y0) > 0.5 * min(r[3] - r[1], y1 - y0)
            g = max(gap, int(0.7 * max(r[3] - r[1], y1 - y0)))
            if same_line and x0 - r[2] <= g and r[0] - x1 <= g:
                r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
                break
        else:
            runs.append([x0, y0, x1, y1])
    return runs


def segment(img: Image.Image, scale: int = 2, depth: int = 0, bg=None, origin=(0, 0)) -> dict:
    """Returns {'bg': rgb, 'boxes': [{x,y,w,h,fill}], 'texts': [{x,y,w,h,color}]} in source pixels."""
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    H, W = arr.shape[:2]
    small = arr[::scale, ::scale]
    if bg is None:
        border = np.concatenate([small[:2].reshape(-1, 3), small[-2:].reshape(-1, 3), small[:, :2].reshape(-1, 3), small[:, -2:].reshape(-1, 3)])
        bg = _dominant(border)
    diff = np.abs(small - np.asarray(bg)).sum(-1)
    mask = diff > 9
    comps = components(mask, min_px=2)
    boxes, glyphs = [], []
    ox, oy = origin
    for x0, y0, x1, y1, n in comps:
        w, h = x1 - x0, y1 - y0
        fill_ratio = n / max(w * h, 1)
        X0, Y0, X1, Y1 = x0 * scale, y0 * scale, x1 * scale, y1 * scale
        if w * h >= 120 and fill_ratio > 0.6 and w * scale >= 14 and (h * scale >= 24 or (w * scale >= 60 and h * scale >= 14)):
            reg = arr[Y0:Y1, X0:X1]
            fill = _dominant(reg)
            box = {"x": X0 + ox, "y": Y0 + oy, "w": X1 - X0, "h": Y1 - Y0, "fill": fill.tolist(), "children": None}
            if depth < 1 and (X1 - X0) > 24 and (Y1 - Y0) > 14:
                inner = segment(Image.fromarray(reg.astype(np.uint8)), scale, depth + 1, bg=fill, origin=(X0 + ox, Y0 + oy))
                box["children"] = inner
            boxes.append(box)
        elif h * scale <= 48:
            glyphs.append((X0, Y0, X1, Y1, n))
    texts = []
    for x0, y0, x1, y1 in _merge_text(glyphs, gap=12):
        reg = arr[y0:y1, x0:x1].reshape(-1, 3)
        d = np.abs(reg - np.asarray(bg)).sum(-1)
        color = reg[d.argmax()] if len(reg) else np.array([0, 0, 0])
        texts.append({"x": x0 + ox, "y": y0 + oy, "w": x1 - x0, "h": y1 - y0, "color": color.tolist()})
    return {"bg": [float(v) for v in bg], "boxes": boxes, "texts": texts, "w": W, "h": H}
