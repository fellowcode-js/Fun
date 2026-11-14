"""Accessible palettes and type scales with computed (never guessed) WCAG contrast."""
from __future__ import annotations

import colorsys
import re

AA_NORMAL, AA_LARGE, AAA_NORMAL = 4.5, 3.0, 7.0


def parse_color(s) -> tuple[float, float, float, float]:
    """'#rgb', '#rrggbb', '#rrggbbaa', 'rgb(...)', 'rgba(...)' or (r,g,b) -> (r,g,b,a) in 0..255 / 0..1 alpha."""
    if isinstance(s, (tuple, list)):
        return (float(s[0]), float(s[1]), float(s[2]), float(s[3]) if len(s) > 3 else 1.0)
    s = s.strip().lower()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (r, g, b, a)
    m = re.match(r"rgba?\(([^)]+)\)", s)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        r, g, b = (float(p) for p in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return (r, g, b, a)
    named = {"white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0), "transparent": (0, 0, 0)}
    if s in named:
        return (*named[s], 0.0 if s == "transparent" else 1.0)
    raise ValueError(f"unparseable color {s!r}")


def to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(round(max(0, min(255, c)))) for c in rgb[:3])


def blend(fg, bg) -> tuple[float, float, float]:
    """Composite a possibly translucent fg over an opaque bg."""
    r, g, b, a = parse_color(fg)
    R, G, B, _ = parse_color(bg)
    return (r * a + R * (1 - a), g * a + G * (1 - a), b * a + B * (1 - a))


def luminance(c) -> float:
    r, g, b, _ = parse_color(c)

    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(fg, bg) -> float:
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def is_large_text(size_px: float, weight: int | str = 400) -> bool:
    w = int(weight) if str(weight).isdigit() else (700 if str(weight) == "bold" else 400)
    return size_px >= 24 or (size_px >= 18.66 and w >= 700)


def passes(fg, bg, size_px: float = 16, weight=400, level: str = "AA") -> bool:
    need = (AA_LARGE if is_large_text(size_px, weight) else AA_NORMAL) if level == "AA" else \
        (4.5 if is_large_text(size_px, weight) else AAA_NORMAL)
    return contrast(fg, bg) >= need


def _hls(c):
    r, g, b, _ = parse_color(c)
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)


def _from_hls(h, l, s) -> str:
    return to_hex(tuple(v * 255 for v in colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))))


def adjust_for_contrast(fg, bg, target: float = AA_NORMAL, max_iter: int = 60) -> str:
    """Move fg lightness away from bg until the contrast target is met (keeps hue)."""
    h, l, s = _hls(fg)
    darker = luminance(bg) > 0.18
    cur = to_hex(parse_color(fg))
    for _ in range(max_iter):
        if contrast(cur, bg) >= target:
            return cur
        l += -0.02 if darker else 0.02
        cur = _from_hls(h, l, s)
        if l <= 0 or l >= 1:
            break
    return "#000000" if darker else "#ffffff"


def generate(base: str = "#3366cc", dark: bool = False, accent_shift: float = 0.5) -> dict:
    """Build an accessible token set around a base color; every text pair is verified."""
    h, l, s = _hls(base)
    if dark:
        bg, surface, text, muted = _from_hls(h, 0.08, 0.15), _from_hls(h, 0.14, 0.15), "#f2f4f7", _from_hls(h, 0.72, 0.1)
    else:
        bg, surface, text, muted = _from_hls(h, 0.97, 0.3), "#ffffff", _from_hls(h, 0.12, 0.2), _from_hls(h, 0.38, 0.1)
    primary = adjust_for_contrast(base, surface, AA_LARGE)
    on_primary = "#ffffff" if contrast("#ffffff", primary) >= contrast("#111111", primary) else "#111111"
    if contrast(on_primary, primary) < AA_NORMAL:
        primary = adjust_for_contrast(primary, on_primary, AA_NORMAL)
    accent = adjust_for_contrast(_from_hls((h + accent_shift) % 1, 0.45, s), surface, AA_LARGE)
    muted = adjust_for_contrast(muted, surface, AA_NORMAL)
    tokens = {"bg": bg, "surface": surface, "text": text, "muted": muted, "primary": primary,
              "on-primary": on_primary, "accent": accent}
    checks = {
        "text/bg": contrast(text, bg), "text/surface": contrast(text, surface), "muted/surface": contrast(muted, surface),
        "on-primary/primary": contrast(on_primary, primary), "primary/surface": contrast(primary, surface),
        "accent/surface": contrast(accent, surface),
    }
    need = {"text/bg": 4.5, "text/surface": 4.5, "muted/surface": 4.5, "on-primary/primary": 4.5,
            "primary/surface": 3.0, "accent/surface": 3.0}
    return {"tokens": tokens, "checks": {k: {"ratio": round(v, 2), "need": need[k], "pass": v >= need[k]} for k, v in checks.items()}}


def type_scale(base_px: float = 16, ratio: float = 1.25, steps_up: int = 5, steps_down: int = 2) -> dict:
    names_up = ["lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl"]
    names_down = ["sm", "xs", "2xs"]
    scale = {"base": round(base_px, 2)}
    for i in range(1, steps_up + 1):
        scale[names_up[i - 1]] = round(base_px * ratio ** i, 2)
    for i in range(1, steps_down + 1):
        scale[names_down[i - 1]] = round(base_px / ratio ** i, 2)
    issues = [f"{k}={v}px is below 12px minimum for body text" for k, v in scale.items() if v < 12]
    line = {k: round(1.5 if v <= 20 else 1.25 if v <= 32 else 1.1, 2) for k, v in scale.items()}
    return {"sizes": scale, "line_height": line, "ratio": ratio, "issues": issues}


def to_css(tokens: dict, scale: dict | None = None) -> str:
    lines = [":root {"] + [f"  --color-{k}: {v};" for k, v in tokens.items()]
    if scale:
        lines += [f"  --font-{k}: {v}px;" for k, v in scale["sizes"].items()]
    return "\n".join(lines + ["}"])
