"""Procedural object images (license-clean) for general recognition: shapes in colors, with captions."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

SHAPES = ["circle", "square", "triangle", "star", "heart", "arrow", "cross", "ring", "hexagon", "moon"]
COLORS = {"red": (220, 40, 40), "green": (40, 170, 70), "blue": (40, 90, 220), "yellow": (235, 200, 30),
          "purple": (140, 60, 190), "orange": (240, 130, 30), "black": (25, 25, 25), "teal": (20, 160, 160)}


def _poly(cx, cy, r, n, rot=0.0):
    return [(cx + r * math.cos(rot + 2 * math.pi * i / n), cy + r * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)]


def draw_shape(d: ImageDraw.ImageDraw, shape: str, cx: float, cy: float, r: float, color, bg, rot: float):
    if shape == "circle":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    elif shape == "square":
        d.polygon(_poly(cx, cy, r * 1.2, 4, rot + math.pi / 4), fill=color)
    elif shape == "triangle":
        d.polygon(_poly(cx, cy, r * 1.15, 3, rot - math.pi / 2), fill=color)
    elif shape == "hexagon":
        d.polygon(_poly(cx, cy, r, 6, rot), fill=color)
    elif shape == "star":
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            a = rot - math.pi / 2 + i * math.pi / 5
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=color)
    elif shape == "ring":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        d.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], fill=bg)
    elif shape == "moon":
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        o = r * 0.55
        d.ellipse([cx - r + o * math.cos(rot), cy - r + o * math.sin(rot), cx + r + o * math.cos(rot), cy + r + o * math.sin(rot)], fill=bg)
    elif shape == "cross":
        w = r * 0.38
        for a in (rot, rot + math.pi / 2):
            ca, sa = math.cos(a), math.sin(a)
            pts = [(cx + ca * r - sa * w, cy + sa * r + ca * w), (cx + ca * r + sa * w, cy + sa * r - ca * w),
                   (cx - ca * r + sa * w, cy - sa * r - ca * w), (cx - ca * r - sa * w, cy - sa * r + ca * w)]
            d.polygon(pts, fill=color)
    elif shape == "heart":
        s = r * 0.55
        d.ellipse([cx - 2 * s, cy - 1.6 * s, cx, cy + 0.4 * s], fill=color)
        d.ellipse([cx, cy - 1.6 * s, cx + 2 * s, cy + 0.4 * s], fill=color)
        d.polygon([(cx - 1.95 * s, cy - 0.3 * s), (cx + 1.95 * s, cy - 0.3 * s), (cx, cy + 2 * s)], fill=color)
    elif shape == "arrow":
        ca, sa = math.cos(rot), math.sin(rot)
        def T(x, y):
            return (cx + x * ca - y * sa, cy + x * sa + y * ca)
        pts = [(-r, -r * 0.25), (r * 0.2, -r * 0.25), (r * 0.2, -r * 0.65), (r, 0), (r * 0.2, r * 0.65), (r * 0.2, r * 0.25), (-r, r * 0.25)]
        d.polygon([T(*p) for p in pts], fill=color)


def make(seed: int, size: int = 64, shape: str | None = None) -> tuple[Image.Image, str, str, str]:
    """Returns (image, shape, color, caption)."""
    rng = random.Random(seed)
    shape = shape or rng.choice(SHAPES)
    cname = rng.choice(list(COLORS))
    bgv = rng.randint(200, 255) if cname != "black" or rng.random() < 0.8 else rng.randint(150, 200)
    bg = (bgv, bgv - rng.randint(0, 20), bgv - rng.randint(0, 25))
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(0, 3)):  # clutter
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        d.line([x, y, x + rng.uniform(-20, 20), y + rng.uniform(-20, 20)], fill=tuple(rng.randint(120, 230) for _ in range(3)), width=1)
    r = rng.uniform(size * 0.22, size * 0.36)
    cx, cy = rng.uniform(r, size - r), rng.uniform(r, size - r)
    jitter = tuple(max(0, min(255, c + rng.randint(-25, 25))) for c in COLORS[cname])
    draw_shape(d, shape, cx, cy, r, jitter, bg, rng.uniform(0, 2 * math.pi))
    if rng.random() < 0.3:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
    caption = rng.choice(["a {c} {s}", "{c} {s} icon", "photo of a {c} {s}", "the {s} shape in {c}"]).format(c=cname, s=shape)
    return img, shape, cname, caption
