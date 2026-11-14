"""design.tokens: extract colors, spacing, radii and fonts from a page into a design-token file."""
from __future__ import annotations

import json
from collections import Counter

from xon.design import palette


def from_styles(styles: list[dict]) -> dict:
    colors, bgs, fonts, sizes, spacing, radii = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    for el in styles:
        area = max(el["w"] * el["h"], 1)
        try:
            if el.get("text"):
                colors[palette.to_hex(palette.parse_color(el["color"]))] += len(el["text"])
                fonts[el["font"].split(",")[0].strip("'\" ")] += 1
                sizes[round(el["size"])] += 1
            c = palette.parse_color(el["bg"])
            if c[3] > 0.5:
                bgs[palette.to_hex(c)] += area
        except ValueError:
            pass
        for v in el.get("pad", []) + el.get("margin", []):
            if v and v > 0:
                spacing[round(v)] += 1
        if el.get("radius"):
            radii[round(el["radius"])] += 1
    body = next((el for el in styles if el["tag"] == "body"), None)
    body_bg = palette.parse_color(body["bg"]) if body else (0, 0, 0, 0)
    bg = palette.to_hex(body_bg) if body_bg[3] > 0.5 else (bgs.most_common(1)[0][0] if bgs else "#ffffff")
    text = colors.most_common(1)[0][0] if colors else "#000000"
    accents = [c for c, _ in bgs.most_common(8) if c != bg and palette.contrast(c, bg) > 1.8][:3]
    tokens = {
        "color": {"background": bg, "text": text, **{f"accent-{i + 1}": c for i, c in enumerate(accents)},
                  **{f"text-{i + 2}": c for i, (c, _) in enumerate(colors.most_common(4)[1:])}},
        "font": {"family": [f for f, _ in fonts.most_common(3)], "size": sorted(sizes)[:8]},
        "space": sorted(v for v, n in spacing.most_common(8)),
        "radius": sorted(radii)[:4],
        "contrast": {"text/background": round(palette.contrast(text, bg), 2)},
    }
    return tokens


def from_html(html: str, renderer=None) -> dict:
    from xon.design.render import Renderer
    own = renderer is None
    r = renderer or Renderer().__enter__()
    try:
        res = r.render(html, styles=True)
    finally:
        if own:
            r.__exit__(None, None, None)
    return from_styles(res["styles"])


def to_css(tokens: dict) -> str:
    lines = [":root {"]
    for k, v in tokens["color"].items():
        lines.append(f"  --color-{k}: {v};")
    for i, v in enumerate(tokens["space"]):
        lines.append(f"  --space-{i + 1}: {v}px;")
    for i, v in enumerate(tokens["radius"]):
        lines.append(f"  --radius-{i + 1}: {v}px;")
    if tokens["font"]["family"]:
        lines.append(f"  --font-family: {', '.join(json.dumps(f) for f in tokens['font']['family'])};")
    return "\n".join(lines + ["}"])
