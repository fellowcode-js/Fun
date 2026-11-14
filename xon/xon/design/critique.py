"""design.critique: structured feedback on hierarchy, spacing, contrast, alignment, consistency, accessibility.
Contrast ratios are computed from computed styles (HTML mode) or measured pixels (screenshot mode)."""
from __future__ import annotations

from collections import Counter

import numpy as np

from xon.design import palette

TEXT_TAGS = {"p", "span", "a", "button", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "label", "div", "strong", "em", "small"}


def _bg_for(el: dict, styles: list[dict], page_bg: str = "rgb(255, 255, 255)") -> str:
    """Effective background: smallest opaque element whose box contains el (including itself)."""
    best, best_area = None, float("inf")
    for s in styles:
        try:
            a = palette.parse_color(s["bg"])[3]
        except ValueError:
            continue
        if a < 0.5:
            continue
        if s["x"] <= el["x"] + 0.5 and s["y"] <= el["y"] + 0.5 and s["x"] + s["w"] >= el["x"] + el["w"] - 0.5 and s["y"] + s["h"] >= el["y"] + el["h"] - 0.5:
            area = s["w"] * s["h"]
            if area < best_area:
                best, best_area = s["bg"], area
    return best or page_bg


def critique_styles(styles: list[dict], page_bg: str = "rgb(255, 255, 255)", html: str = "") -> dict:
    issues: list[dict] = []
    # --- contrast (computed)
    checked = failed = 0
    for el in styles:
        if not el.get("text") or el["tag"] not in TEXT_TAGS:
            continue
        bg = _bg_for(el, styles, page_bg)
        fg = palette.blend(el["color"], bg)
        ratio = palette.contrast(fg, bg)
        need = palette.AA_LARGE if palette.is_large_text(el["size"], el["weight"]) else palette.AA_NORMAL
        checked += 1
        if ratio < need:
            failed += 1
            issues.append({"category": "contrast", "severity": "high" if ratio < 3 else "medium",
                           "element": f"<{el['tag']}> '{el['text'][:30]}'", "ratio": round(ratio, 2), "need": need,
                           "fix": f"text {palette.to_hex(fg)} on {palette.to_hex(palette.parse_color(bg))}: use "
                                  f"{palette.adjust_for_contrast(palette.to_hex(fg), palette.to_hex(palette.parse_color(bg)), need)}"})
    # --- touch targets (WCAG 2.2 AA 2.5.8: 24x24 CSS px)
    for el in styles:
        if el["tag"] in ("button", "a", "input", "select") and (el["w"] < 24 or el["h"] < 24) and el["tag"] != "a":
            issues.append({"category": "accessibility", "severity": "medium", "element": f"<{el['tag']}> '{el['text'][:20]}'",
                           "detail": f"target {el['w']:.0f}x{el['h']:.0f}px < 24x24px"})
    # --- labels / alt / names
    for el in styles:
        if el["tag"] == "img" and not el.get("alt"):
            issues.append({"category": "accessibility", "severity": "high", "element": "<img>", "detail": "missing alt text"})
        if el["tag"] in ("input", "textarea", "select") and el.get("type") not in ("hidden", "submit", "button") and not el.get("labelled"):
            issues.append({"category": "accessibility", "severity": "high", "element": f"<{el['tag']}>", "detail": "form field has no label/aria-label"})
        if el["tag"] == "button" and not el.get("text") and not el.get("aria"):
            issues.append({"category": "accessibility", "severity": "high", "element": "<button>", "detail": "button has no accessible name"})
    if html and "<html" in html and "lang=" not in html.split(">")[0] + html[:300]:
        issues.append({"category": "accessibility", "severity": "low", "element": "<html>", "detail": "missing lang attribute"})
    # --- hierarchy
    sizes = {}
    for el in styles:
        if el["tag"] in ("h1", "h2", "h3", "p") and el.get("text"):
            sizes.setdefault(el["tag"], []).append(el["size"])
    order = [t for t in ("h1", "h2", "h3", "p") if t in sizes]
    for a, b in zip(order, order[1:]):
        if max(sizes[a]) <= max(sizes[b]):
            issues.append({"category": "hierarchy", "severity": "medium", "element": f"<{a}> vs <{b}>",
                           "detail": f"{a} ({max(sizes[a]):.0f}px) not larger than {b} ({max(sizes[b]):.0f}px)"})
    n_h1 = len(sizes.get("h1", []))
    if n_h1 == 0 and styles:
        issues.append({"category": "hierarchy", "severity": "low", "element": "page", "detail": "no <h1>: unclear primary heading"})
    elif n_h1 > 1:
        issues.append({"category": "hierarchy", "severity": "low", "element": "page", "detail": f"{n_h1} <h1> elements compete for attention"})
    # --- spacing consistency (4px grid, number of distinct values)
    sp = [round(v) for el in styles for v in (el.get("pad", []) + el.get("margin", [])) if v and v > 0]
    off_grid = [v for v in sp if v % 4 not in (0,)]
    distinct = sorted(set(sp))
    if sp and len(off_grid) / len(sp) > 0.3:
        issues.append({"category": "spacing", "severity": "low", "element": "page",
                       "detail": f"{len(off_grid)}/{len(sp)} padding/margin values are off a 4px grid (e.g. {sorted(set(off_grid))[:5]})"})
    if len(distinct) > 10:
        issues.append({"category": "spacing", "severity": "low", "element": "page", "detail": f"{len(distinct)} distinct spacing values; use a scale"})
    # --- alignment: left edges that almost (1-3px) but not exactly line up
    xs = sorted(round(el["x"]) for el in styles if el["w"] > 20 and el["tag"] in TEXT_TAGS | {"section", "form", "table", "input"})
    near = 0
    for a, b in zip(xs, xs[1:]):
        if 0 < b - a <= 3:
            near += 1
    if near >= 2:
        issues.append({"category": "alignment", "severity": "low", "element": "page", "detail": f"{near} left edges are 1-3px off each other"})
    # --- consistency
    fonts = Counter(el["font"].split(",")[0].strip("'\" ") for el in styles if el.get("text"))
    if len(fonts) > 2:
        issues.append({"category": "consistency", "severity": "low", "element": "page", "detail": f"{len(fonts)} font families: {list(fonts)[:4]}"})
    btn_bg = Counter(el["bg"] for el in styles if el["tag"] == "button")
    if len(btn_bg) > 3:
        issues.append({"category": "consistency", "severity": "low", "element": "buttons", "detail": f"{len(btn_bg)} different button colors"})
    radii = Counter(round(el.get("radius", 0)) for el in styles if el["tag"] in ("button", "input"))
    if len(radii) > 2:
        issues.append({"category": "consistency", "severity": "low", "element": "controls", "detail": f"{len(radii)} different corner radii on controls"})
    weights = {"high": 12, "medium": 6, "low": 2}
    score = max(0, 100 - sum(weights[i["severity"]] for i in issues))
    cats = Counter(i["category"] for i in issues)
    return {"score": score, "mode": "computed-styles", "contrast_checked": checked, "contrast_failed": failed,
            "issues": issues, "by_category": dict(cats)}


def critique_html(html: str, renderer=None, width: int = 640, height: int = 480) -> dict:
    from xon.design.render import Renderer
    own = renderer is None
    r = renderer or Renderer(width, height).__enter__()
    try:
        res = r.render(html, width, height, styles=True)
    finally:
        if own:
            r.__exit__(None, None, None)
    page_bg = next((s["bg"] for s in res["styles"] if s["tag"] == "body"), "rgb(255, 255, 255)")
    if palette.parse_color(page_bg)[3] < 0.5:
        page_bg = "rgb(255, 255, 255)"
    out = critique_styles(res["styles"], page_bg, html)
    out["image"] = res["image"]
    return out


def critique_file(path, renderer=None, interact: bool = False, width: int = 640, height: int = 480) -> dict:
    """Critique a page loaded from disk (scripts and relative assets work). interact=True fills the first
    text input + submits a few times so dynamic content (lists, counters) is critiqued too."""
    from pathlib import Path

    from xon.design.render import Renderer
    own = renderer is None
    r = renderer or Renderer(width, height).__enter__()
    try:
        page = r._page
        page.set_viewport_size({"width": width, "height": height})
        page.goto(Path(path).resolve().as_uri(), wait_until="load")
        if interact:
            inp = page.locator("form input[type=text], form input:not([type])")
            if inp.count():
                for t in ("Buy milk", "Write report", "Call Sam"):
                    inp.first.fill(t)
                    inp.first.press("Enter")
        from xon.design.render import _STYLES_JS
        import io
        from PIL import Image
        styles = page.evaluate(_STYLES_JS)
        img = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    finally:
        if own:
            r.__exit__(None, None, None)
    page_bg = next((s["bg"] for s in styles if s["tag"] == "body"), "rgb(255, 255, 255)")
    if palette.parse_color(page_bg)[3] < 0.5:
        page_bg = "rgb(255, 255, 255)"
    out = critique_styles(styles, page_bg, Path(path).read_text())
    out["image"] = img
    return out


def _two_colors(region: np.ndarray):
    px = region.reshape(-1, 3).astype(np.float64)
    if len(px) < 4:
        return None
    a, b = px[np.argmin(px.sum(1))], px[np.argmax(px.sum(1))]
    for _ in range(8):
        da, db = ((px - a) ** 2).sum(1), ((px - b) ** 2).sum(1)
        ma = da < db
        if ma.all() or (~ma).all():
            break
        a, b = px[ma].mean(0), px[~ma].mean(0)
    ma = ((px - a) ** 2).sum(1) < ((px - b) ** 2).sum(1)
    major, minor = (a, b) if ma.mean() >= 0.5 else (b, a)
    return major, minor


def critique_image(img, vision_model=None) -> dict:
    """Screenshot-only critique: detected elements + pixel-measured contrast (bg = majority color, fg = minority)."""
    arr = np.asarray(img.convert("RGB"))
    issues, dets = [], []
    if vision_model is not None:
        from xon.vision.predict import detect
        dets = detect(vision_model, img)
    regions = [d for d in dets if d["label"] in ("button", "nav", "card", "input")] or \
              [{"label": "page", "x": 0, "y": 0, "w": img.size[0], "h": img.size[1], "score": 1.0}]
    measured = []
    for d in regions:
        x0, y0 = max(0, int(d["x"])), max(0, int(d["y"]))
        x1, y1 = min(arr.shape[1], int(d["x"] + d["w"])), min(arr.shape[0], int(d["y"] + d["h"]))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        tc = _two_colors(arr[y0:y1, x0:x1])
        if tc is None:
            continue
        bg, fg = tc
        ratio = palette.contrast(tuple(fg), tuple(bg))
        measured.append({"label": d["label"], "ratio": round(ratio, 2)})
        if d["label"] == "button" and ratio < palette.AA_NORMAL:
            issues.append({"category": "contrast", "severity": "high" if ratio < 3 else "medium", "element": f"{d['label']} at ({x0},{y0})",
                           "ratio": round(ratio, 2), "need": 4.5, "detail": "measured from pixels (text antialiasing lowers it slightly)"})
    labels = Counter(d["label"] for d in dets)
    if dets and "nav" not in labels:
        issues.append({"category": "hierarchy", "severity": "low", "element": "page", "detail": "no navigation detected"})
    if labels.get("button", 0) > 6:
        issues.append({"category": "hierarchy", "severity": "low", "element": "buttons", "detail": f"{labels['button']} buttons compete; pick one primary action"})
    weights = {"high": 12, "medium": 6, "low": 2}
    return {"score": max(0, 100 - sum(weights[i["severity"]] for i in issues)), "mode": "pixels+vision",
            "detected": dict(labels), "measured_contrast": measured, "issues": issues}


def improve_html(html: str, report: dict) -> str:
    """Apply mechanical fixes from a critique: contrast colors, missing lang, input labels, tiny targets."""
    import re
    out = html
    for i in report["issues"]:
        if i["category"] == "contrast" and "fix" in i:
            m = re.match(r"text (#[0-9a-f]{6}) on (#[0-9a-f]{6}): use (#[0-9a-f]{6})", i["fix"])
            if m:
                fg, bg, new = m.groups()
                # replace foreground color declarations equal to fg (case-insensitive)
                out = re.sub(rf"color:\s*{fg}\b", f"color:{new}", out, flags=re.I)
                if fg in ("#ffffff",) and new != fg:  # white text on a light button: darken the background instead
                    darker = palette.adjust_for_contrast(bg, "#ffffff", i["need"])
                    out = re.sub(rf"background:\s*{bg}\b", f"background:{darker}", out, flags=re.I)
                    out = re.sub(rf"background-color:\s*{bg}\b", f"background-color:{darker}", out, flags=re.I)
    if '<html lang=' not in out:
        out = out.replace("<html>", '<html lang="en">', 1)
    out = re.sub(r"<input(?![^>]*aria-label)([^>]*placeholder=\"([^\"]+)\")", r'<input aria-label="\2"\1', out)
    return out
