"""design.from_screenshot: reference screenshot -> HTML/CSS approximation, then iterate:
render -> compare (perceptual similarity) -> adjust, until close or a step limit hits.

Geometry comes from pixel segmentation (uniform boxes + text runs); semantics (button, input, nav, card,
table, modal, icon) from the vision net's UI detector where they overlap."""
from __future__ import annotations

import copy

import numpy as np
from PIL import Image

from xon.design.segment import segment
from xon.design.similarity import fidelity
from xon.vision.ui_detect import iou

WORDS = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor".split()


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c[:3])


def _label_for(box: dict, dets: list[dict]) -> str:
    best, lab = 0.0, "div"
    for d in dets:
        v = iou((box["x"], box["y"], box["w"], box["h"]), (d["x"], d["y"], d["w"], d["h"]))
        if v > best:
            best, lab = v, d["label"]
    return lab if best >= 0.4 else "div"


def initial_layout(img: Image.Image, dets: list[dict]) -> dict:
    seg = segment(img)
    W, H = img.size

    def conv(s, out_boxes, out_texts):
        for b in s["boxes"]:
            out_boxes.append({"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "fill": _hex(b["fill"]),
                              "label": _label_for(b, dets), "radius": 6})
            if b["children"]:
                conv(b["children"], out_boxes, out_texts)
        for t in s["texts"]:
            out_texts.append({"x": t["x"], "y": t["y"], "w": t["w"], "h": t["h"], "color": _hex(t["color"]), "scale": 1.0})

    boxes, texts = [], []
    conv(seg, boxes, texts)
    boxes.sort(key=lambda b: -(b["w"] * b["h"]))  # paint large first
    icons = [d for d in dets if d["label"] == "icon"]
    return {"bg": _hex(seg["bg"]), "w": W, "h": H, "boxes": boxes, "texts": texts, "icons": icons, "font": "system-ui, sans-serif"}


def _text_span(t: dict, font: str, i: int) -> str:
    fs = max(8, round(t["h"] * 1.0 * t.get("scale", 1.0)))
    n_chars = max(1, int(t["w"] / (fs * 0.52)))
    words, s, k = [], 0, i
    while s < n_chars:
        w = WORDS[k % len(WORDS)]
        words.append(w)
        s += len(w) + 1
        k += 1
    txt = " ".join(words)[:n_chars]
    weight = 700 if t["h"] >= 20 else 400
    return (f'<span style="position:absolute;left:{t["x"]}px;top:{t["y"] - round(fs * 0.12)}px;width:{t["w"] + 4}px;'
            f'height:{t["h"] + 4}px;overflow:hidden;white-space:nowrap;font:{weight} {fs}px/{t["h"]}px {font};color:{t["color"]}">{txt}</span>')


def layout_to_html(L: dict) -> str:
    parts = []
    for b in L["boxes"]:
        st = (f"position:absolute;left:{b['x']}px;top:{b['y']}px;width:{b['w']}px;height:{b['h']}px;"
              f"background:{b['fill']};border-radius:{b['radius']}px;box-sizing:border-box;")
        lab = b["label"]
        if lab == "button":
            parts.append(f'<button data-xon="button" style="{st}border:0;padding:0"></button>')
        elif lab == "input":
            parts.append(f'<input data-xon="input" aria-label="field" style="{st}border:1px solid #8888">')
        elif lab == "nav":
            parts.append(f'<nav data-xon="nav" style="{st}border-radius:0"></nav>')
        elif lab == "table":
            parts.append(f'<div data-xon="table" style="{st}border-radius:0"></div>')
        elif lab == "modal":
            parts.append(f'<div data-xon="modal" role="dialog" aria-label="dialog" style="{st}"></div>')
        elif lab == "card":
            parts.append(f'<div data-xon="card" style="{st}box-shadow:0 1px 3px #0002"></div>')
        else:
            parts.append(f'<div style="{st}"></div>')
    for i, t in enumerate(L["texts"]):
        parts.append(_text_span(t, L["font"], i))
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><style>body{{margin:0;background:{L["bg"]};'
            f'width:{L["w"]}px;height:{L["h"]}px;position:relative;overflow:hidden}}</style></head><body>' + "".join(parts) + "</body></html>")


def refine(target: Image.Image, L: dict, renderer, steps: int = 8) -> tuple[dict, list[float]]:
    """Coordinate descent on global parameters (font, radius, text scale, box/text subsets); keeps improving moves."""
    W, H = target.size

    def score(LL):
        return fidelity(renderer.screenshot_html(layout_to_html(LL), W, H), target)

    best = score(L)
    hist = [best]
    moves = [
        lambda c: c.update(font="Georgia, serif"),
        lambda c: c.update(font="'Courier New', monospace"),
        lambda c: c.update(font="Verdana, sans-serif"),
        lambda c: [t.update(scale=0.85) for t in c["texts"]],
        lambda c: [t.update(scale=1.15) for t in c["texts"]],
        lambda c: [b.update(radius=0) for b in c["boxes"]],
        lambda c: [b.update(radius=12) for b in c["boxes"]],
        lambda c: c.update(texts=[t for t in c["texts"] if t["w"] > 6]),
        lambda c: c.update(boxes=[b for b in c["boxes"] if b["w"] * b["h"] > 400]),
    ]
    for step, mv in enumerate(moves[:steps]):
        cand = copy.deepcopy(L)
        mv(cand)
        s = score(cand)
        if s > best + 1e-4:
            L, best = cand, s
        hist.append(best)
        if best > 0.97:
            break
    return L, hist


def from_screenshot(target: Image.Image, vision_model, renderer, steps: int = 8, thresh: float = 0.35) -> dict:
    from xon.vision.predict import detect
    target = target.convert("RGB")
    dets = detect(vision_model, target, thresh) if vision_model is not None else []
    L0 = initial_layout(target, dets)
    W, H = target.size
    blank = {"bg": L0["bg"], "w": W, "h": H, "boxes": [], "texts": [], "icons": [], "font": L0["font"]}
    base_score = fidelity(renderer.screenshot_html(layout_to_html(blank), W, H), target)
    L, hist = refine(target, L0, renderer, steps)
    html = layout_to_html(L)
    return {"html": html, "layout": L, "detections": len(dets), "boxes": len(L["boxes"]), "texts": len(L["texts"]),
            "baseline_bg_only": base_score, "initial": hist[0], "final": hist[-1], "history": hist}
