"""design.from_screenshot: reference screenshot -> HTML/CSS approximation, then iterate:
render -> compare (perceptual similarity) -> adjust, until close or a step limit hits."""
from __future__ import annotations

import copy

import numpy as np
from PIL import Image

from xon.design.similarity import fidelity


def _dominant(arr: np.ndarray) -> tuple[int, int, int]:
    px = (arr.reshape(-1, 3) // 16).astype(np.int32)
    keys = px[:, 0] * 256 + px[:, 1] * 16 + px[:, 2]
    k = np.bincount(keys).argmax()
    sel = arr.reshape(-1, 3)[keys == k]
    return tuple(int(v) for v in sel.mean(0))


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)


def initial_layout(img: Image.Image, dets: list[dict]) -> dict:
    arr = np.asarray(img.convert("RGB"))
    H, W = arr.shape[:2]
    border = np.concatenate([arr[:, :4].reshape(-1, 3), arr[:, -4:].reshape(-1, 3), arr[-4:].reshape(-1, 3)])
    bg = _dominant(border)
    els = []
    for d in sorted(dets, key=lambda d: -(d["w"] * d["h"])):
        x0, y0 = max(0, int(d["x"])), max(0, int(d["y"]))
        x1, y1 = min(W, int(d["x"] + d["w"])), min(H, int(d["y"] + d["h"]))
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        reg = arr[y0:y1, x0:x1]
        fill = _dominant(reg)
        els.append({"label": d["label"], "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "fill": _hex(fill)})
    return {"bg": _hex(bg), "w": W, "h": H, "elements": els, "text": "#222222"}


def layout_to_html(L: dict) -> str:
    parts = []
    for e in L["elements"]:
        st = f"position:absolute;left:{e['x']}px;top:{e['y']}px;width:{e['w']}px;height:{e['h']}px;background:{e['fill']};"
        lab = e["label"]
        if lab == "button":
            parts.append(f'<button data-xon="button" style="{st}border:0;border-radius:6px;color:#fff;font:600 13px sans-serif">Button</button>')
        elif lab == "input":
            parts.append(f'<input data-xon="input" aria-label="field" placeholder="Text" style="{st}border:1px solid #999;border-radius:6px;padding:0 8px;box-sizing:border-box">')
        elif lab == "nav":
            parts.append(f'<nav data-xon="nav" style="{st}border-bottom:1px solid #0002;font:700 16px sans-serif;color:{L["text"]};padding:0 16px;box-sizing:border-box;display:flex;align-items:center">Brand</nav>')
        elif lab == "card":
            parts.append(f'<div data-xon="card" style="{st}border-radius:8px;box-shadow:0 1px 3px #0002;padding:10px;box-sizing:border-box;color:{L["text"]};font:600 15px sans-serif">Title</div>')
        elif lab == "table":
            rows = max(2, e["h"] // 26)
            cols = max(2, e["w"] // 120)
            cells = "".join("<tr>" + "".join('<td style="border:1px solid #9995;padding:4px">x</td>' for _ in range(cols)) + "</tr>" for _ in range(rows))
            parts.append(f'<table data-xon="table" style="{st}border-collapse:collapse;font:13px sans-serif">{cells}</table>')
        elif lab == "modal":
            parts.append(f'<div data-xon="modal" role="dialog" aria-label="dialog" style="{st}border-radius:8px;box-shadow:0 8px 30px #0006"></div>')
        elif lab == "icon":
            parts.append(f'<svg data-xon="icon" style="position:absolute;left:{e["x"]}px;top:{e["y"]}px" width="{e["w"]}" height="{e["h"]}" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="{e["fill"]}" stroke-width="2"/></svg>')
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>body{{margin:0;background:{L["bg"]};'
            f'width:{L["w"]}px;height:{L["h"]}px;position:relative;overflow:hidden}}</style></head><body>' + "".join(parts) + "</body></html>")


def refine(target: Image.Image, L: dict, renderer, steps: int = 12) -> tuple[dict, list[float]]:
    """Coordinate descent over element fills, bg and text color; keeps only improving moves."""
    W, H = target.size
    arr_t = np.asarray(target.convert("RGB"))

    def score(LL):
        return fidelity(renderer.screenshot_html(layout_to_html(LL), W, H), target)

    best = score(L)
    hist = [best]
    for step in range(steps):
        improved = False
        cand = copy.deepcopy(L)
        # 1) re-sample fills from the target, excluding pixels covered by children
        if step == 0:
            for e in cand["elements"]:
                reg = arr_t[e["y"]:e["y"] + e["h"], e["x"]:e["x"] + e["w"]]
                if reg.size:
                    e["fill"] = _hex(np.median(reg.reshape(-1, 3), 0))
        # 2) try removing the weakest element / swapping text color
        elif step % 3 == 1 and cand["elements"]:
            idx = (step // 3) % len(cand["elements"])
            cand["elements"].pop(idx)
        elif step % 3 == 2:
            cand["text"] = "#f2f4f7" if cand["text"] == "#222222" else "#222222"
        else:
            for e in cand["elements"]:
                e["x"], e["y"] = max(0, e["x"] + (1 if step % 2 else -1)), e["y"]
        s = score(cand)
        if s > best + 1e-4:
            L, best, improved = cand, s, True
        hist.append(best)
        if best > 0.97:
            break
        _ = improved
    return L, hist


def from_screenshot(target: Image.Image, vision_model, renderer, steps: int = 12, thresh: float = 0.35) -> dict:
    from xon.vision.predict import detect
    dets = detect(vision_model, target, thresh) if vision_model is not None else []
    L0 = initial_layout(target, dets)
    W, H = target.size
    blank = {"bg": L0["bg"], "w": W, "h": H, "elements": [], "text": "#222222"}
    base_score = fidelity(renderer.screenshot_html(layout_to_html(blank), W, H), target)
    L, hist = refine(target, L0, renderer, steps)
    html = layout_to_html(L)
    return {"html": html, "layout": L, "detections": len(dets), "baseline_bg_only": base_score,
            "initial": hist[0], "final": hist[-1], "history": hist}
