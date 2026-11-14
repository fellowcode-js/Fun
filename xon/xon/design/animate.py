"""XON's animation engine: a description -> a looping animation, made locally (no model, no network).

  spec = parse("a red ball bouncing, slow")            # subject, motions, colour, speed, count, background
  out = render(spec, "anim/ball")                       # anim/ball.html (SVG + CSS), anim/ball.gif, anim/ball.json

One motion function drives both outputs: the CSS keyframes are sampled from it and the GIF frames are drawn from it,
so the web version and the GIF always match. Animation basics are built in: easing, squash and stretch on impact,
a contact shadow, follow-through on limbs, phase offsets for groups, and `prefers-reduced-motion` support.

Subjects: ball, square, triangle, star, heart, ring, diamond, text ("..."), loading dots, spinner, stick figure.
Motions:  bounce, jump, spin, pulse (heartbeat), slide, float, orbit, shake, fade, grow, walk, wave (hand), run.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

COLORS = {"red": "#e5484d", "orange": "#f76b15", "yellow": "#ffc53d", "gold": "#e2a336", "green": "#30a46c",
          "lime": "#99d52a", "teal": "#12a594", "cyan": "#00a2c7", "blue": "#3e63dd", "navy": "#1e3a8a",
          "purple": "#8e4ec6", "violet": "#6e56cf", "pink": "#e93d82", "magenta": "#d6409f", "brown": "#a0612b",
          "black": "#1c1c1c", "white": "#f5f5f5", "gray": "#8b8d98", "grey": "#8b8d98", "silver": "#c1c4cc"}
SUBJECTS = {
    "stickman": r"stick ?(figure|man|person)|stickman|person|man|woman|character|guy|kid|human",
    "dots": r"loading dots|dots|loader|typing indicator",
    "spinner": r"spinner|loading (circle|ring|wheel)|throbber",
    "heart": r"hearts?",
    "star": r"stars?",
    "square": r"squares?|box(es)?|cubes?|blocks?",
    "triangle": r"triangles?",
    "diamond": r"diamonds?|gems?",
    "ring": r"rings?|donuts?|circle outline",
    "ball": r"balls?|circles?|orbs?|bubbles?|planets?|dots?",
}
MOTIONS = {
    "bounce": r"bounc\w*|bouncy", "jump": r"jump\w*|hop\w*", "spin": r"spin\w*|rotat\w*|twirl\w*|turn\w*",
    "pulse": r"puls\w*|heartbeat|beat\w*|throb\w*|breath\w*", "slide": r"slid\w*|mov\w* (left|right|across|side)|swing\w*|sway\w*",
    "float": r"float\w*|hover\w*|bob\w*|drift\w*", "orbit": r"orbit\w*|circl\w* around|go\w* around",
    "shake": r"shak\w*|wiggl\w*|jiggl\w*|vibrat\w*|wobbl\w*", "fade": r"fad\w*|blink\w*|flash\w*|glow\w*",
    "grow": r"grow\w*|shrink\w*|zoom\w*|scal\w*", "walk": r"walk\w*|stroll\w*|march\w*", "run": r"run\w*|sprint\w*|jog\w*",
    "wave": r"wav(e|es|ing)( hello| hi| goodbye)?|hello|greet\w*",
}
DEFAULT_MOTION = {"ball": ["bounce"], "stickman": ["walk"], "dots": ["pulse"], "spinner": ["spin"], "heart": ["pulse"],
                  "star": ["spin", "pulse"], "text": ["float"], "square": ["spin"], "triangle": ["spin"],
                  "diamond": ["float", "spin"], "ring": ["pulse"]}
WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a couple of": 2, "several": 4, "many": 6}


class Refused(ValueError):
    pass


@dataclass
class AnimSpec:
    subject: str = "ball"
    motions: list[str] = field(default_factory=lambda: ["bounce"])
    color: str = "#3e63dd"
    background: str = "#14151a"
    count: int = 1
    duration: float = 1.6
    text: str = ""
    width: int = 480
    height: int = 320
    title: str = "Animation"

    def to_dict(self):
        return asdict(self)


def parse(prompt: str) -> AnimSpec:
    from xon.design import brand
    msg = brand.check(prompt)
    if msg:
        raise Refused(msg)
    if re.search(r"\b(mickey|mario|pikachu|sonic|spongebob|homer simpson|elsa|batman|spider-?man|superman|minion)\b", prompt, re.I):
        raise Refused("XON won't animate a copyrighted character. Describe an original character instead "
                      "(for example 'a stick figure in a red cap waving').")
    p = prompt.lower()
    s = AnimSpec()
    q = re.search(r"[\"“']([^\"”']{1,40})[\"”']", prompt)
    if q and re.search(r"\b(text|word|title|says?|saying|logo text|letters?)\b", p):
        s.subject, s.text = "text", q.group(1)
    else:
        hits = []
        for name, rx in SUBJECTS.items():
            m = re.search(rf"\b({rx})\b", p)
            if m:
                hits.append((m.start(), name))
        if hits:
            s.subject = min(hits)[1] if not any(n == "stickman" for _, n in hits) else "stickman"
            if any(n == "dots" for _, n in hits) and re.search(r"loading|loader|typing", p):
                s.subject = "dots"
    s.motions = [m for m, rx in MOTIONS.items() if re.search(rf"\b({rx})", p)]
    if s.subject != "stickman":
        s.motions = [m for m in s.motions if m not in ("walk", "run", "wave")] or s.motions
        if s.motions in (["walk"], ["run"], ["wave"]):
            s.motions = ["slide"] if s.motions != ["wave"] else ["float"]
    if not s.motions:
        s.motions = list(DEFAULT_MOTION[s.subject])
    if "bounce" in s.motions and "jump" in s.motions:
        s.motions.remove("jump")
    cols = [(m.start(), m.group(1)) for m in re.finditer(r"\b(" + "|".join(COLORS) + r")\b", p)]
    hexes = re.findall(r"#[0-9a-fA-F]{6}\b", prompt)
    if hexes:
        s.color = hexes[0]
    elif cols:
        s.color = COLORS[min(cols)[1]]
    bg = re.search(r"\bon (?:a |an )?(" + "|".join(COLORS) + r"|light|dark|white|black) (?:background|bg|sky|backdrop)", p)
    if bg:
        s.background = {"light": "#f4f2ee", "dark": "#14151a"}.get(bg.group(1), COLORS.get(bg.group(1), "#14151a"))
    elif re.search(r"\b(light|white) (background|bg|theme)\b", p):
        s.background = "#f4f2ee"
    n = re.search(r"\b(\d+)\s+(?:\w+\s+)?(?:" + "|".join(SUBJECTS.values()) + r")", p)
    if n:
        s.count = int(n.group(1))
    else:
        for w, v in WORDNUM.items():
            if re.search(rf"\b{w}\b", p):
                s.count = v
    if s.subject == "dots" and not n:
        s.count = 3
    s.count = max(1, min(s.count, 8 if s.subject != "stickman" else 3))
    secs = re.search(r"(\d+(?:\.\d+)?)\s*(?:s\b|sec|second)", p)
    if secs:
        s.duration = float(secs.group(1))
    elif re.search(r"\b(very fast|super fast|quick(ly)?|fast|rapid)\b", p):
        s.duration = 0.8
    elif re.search(r"\b(very slow|slow(ly)?|gentle|gently|calm|lazy)\b", p):
        s.duration = 3.0
    elif s.subject == "stickman":
        s.duration = 1.2 if "run" in s.motions else 1.6
    s.duration = max(0.3, min(s.duration, 10.0))
    if contrast(s.color, s.background) < 3.0:  # keep the subject visible on its background
        s.background = "#f4f2ee" if _lum(s.color) < 0.4 else "#14151a"
    s.title = prompt.strip()[:80] or "Animation"
    return s


# ------------------------------------------------------------------------------------------- colour helpers

def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lum(h: str) -> float:
    def c(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ------------------------------------------------------------------------------------------- motion model

def _ease(u: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * u)


def pose(s: AnimSpec, i: int, t: float) -> dict:
    """Transform of object i at loop time t in [0,1): dx, dy, rot (deg), sx, sy, op, plus limb angles."""
    W, H = s.width, s.height
    ph = (i / max(1, s.count)) * (0.5 if s.subject != "dots" else 0.6)  # stagger groups
    tt = (t + ph) % 1.0 if s.subject != "dots" else (t - i * 0.15) % 1.0
    d = {"dx": 0.0, "dy": 0.0, "rot": 0.0, "sx": 1.0, "sy": 1.0, "op": 1.0, "shadow": None}
    m = s.motions
    if "bounce" in m or "jump" in m:
        h = H * (0.38 if "bounce" in m else 0.22)
        y = 4 * tt * (1 - tt)  # parabola: 0 at contact, 1 at top
        d["dy"] -= h * y
        if "bounce" in m:  # squash and stretch
            if y < 0.12:
                k = 1 - y / 0.12
                d["sx"], d["sy"] = 1 + 0.28 * k, 1 - 0.28 * k
            else:
                st = min(1.0, (0.6 - min(y, 0.6)) / 0.5) * 0.12
                d["sx"], d["sy"] = 1 - st, 1 + st
        d["shadow"] = 1 - 0.6 * y
    if "spin" in m:
        d["rot"] += 360 * tt
    if "pulse" in m:
        if s.subject == "heart":  # double heartbeat
            b = math.exp(-((tt - 0.12) / 0.05) ** 2) + 0.7 * math.exp(-((tt - 0.32) / 0.05) ** 2)
            k = 1 + 0.22 * b
        elif s.subject == "dots":
            k = 1 + 0.45 * max(0.0, math.sin(2 * math.pi * tt)) ** 2
            d["dy"] -= H * 0.05 * max(0.0, math.sin(2 * math.pi * tt)) ** 2
            d["op"] = 0.45 + 0.55 * max(0.0, math.sin(2 * math.pi * tt))
        else:
            k = 1 + 0.18 * math.sin(2 * math.pi * tt)
        d["sx"] *= k
        d["sy"] *= k
    if "grow" in m:
        k = 0.55 + 0.45 * _ease(1 - abs(2 * tt - 1))
        d["sx"] *= k
        d["sy"] *= k
    if "slide" in m:
        d["dx"] += W * 0.3 / max(1, s.count ** 0.5) * math.sin(2 * math.pi * tt)
        d["rot"] += 0 if "spin" in m else 8 * math.cos(2 * math.pi * tt)
    if "float" in m:
        d["dy"] += H * 0.06 * math.sin(2 * math.pi * tt)
        d["rot"] += 0 if "spin" in m else 4 * math.sin(2 * math.pi * tt + 1)
    if "orbit" in m:
        R = min(W, H) * 0.28
        d["dx"] += R * math.cos(2 * math.pi * tt)
        d["dy"] += R * 0.6 * math.sin(2 * math.pi * tt)
    if "shake" in m:
        env = math.sin(math.pi * tt)
        d["dx"] += 7 * env * math.sin(2 * math.pi * 6 * tt)
        d["rot"] += 6 * env * math.sin(2 * math.pi * 6 * tt + 0.5)
    if "fade" in m:
        d["op"] *= 0.15 + 0.85 * _ease(1 - abs(2 * tt - 1))
    if s.subject == "stickman":
        a = 2 * math.pi * tt
        run = "run" in m
        sw = 38 if run else 26
        d.update({"thL": sw * math.sin(a), "thR": -sw * math.sin(a), "shL": max(0, 50 if run else 30) * max(0, -math.cos(a)),
                  "shR": (50 if run else 30) * max(0, math.cos(a)), "arL": -sw * 1.1 * math.sin(a),
                  "arR": sw * 1.1 * math.sin(a), "foL": 25 + 15 * math.sin(a), "foR": 25 - 15 * math.sin(a),
                  "lean": 10 if run else 3})
        if "walk" in m or run:
            d["dx"] += (tt - 0.5) * W * (0.78 if run else 0.7)  # crosses the stage once per loop
            d["dy"] -= abs(math.sin(a)) * (9 if run else 5)  # bob
        else:
            d.update({"thL": 9.0, "thR": -9.0, "shL": 0.0, "shR": 0.0})  # relaxed stance
            d["lean"] = 0
            d["arL"], d["foL"] = 18, 10
        if "wave" in m:
            d["arR"], d["foR"] = -150 + 12 * math.sin(a), -25 + 35 * math.sin(2 * a)
        if "jump" in m or "bounce" in m:
            crouch = max(0.0, 1 - 4 * tt * (1 - tt) * 4) if tt < 0.1 or tt > 0.9 else 0.0
            d["thL"], d["thR"], d["shL"], d["shR"] = -30 * crouch - 10, -30 * crouch - 10, 60 * crouch + 20, 60 * crouch + 20
        if "spin" in m:
            d["rot"] = 360 * tt
    return d


def _layout(s: AnimSpec, i: int) -> tuple[float, float, float]:
    """Centre and size of object i."""
    W, H = s.width, s.height
    n = s.count
    if s.subject == "dots":
        gap = min(W / (n + 1), 46)
        cx = W / 2 + (i - (n - 1) / 2) * gap
        return cx, H / 2, gap * 0.32
    size = min(W, H) * (0.16 if n == 1 else 0.5 / (n + 1))
    cx = W * (i + 1) / (n + 1)
    cy = H * (0.66 if any(x in s.motions for x in ("bounce", "jump")) else 0.5)
    if s.subject == "stickman":
        cy = H * 0.6
        size = min(W, H) * (0.28 if n == 1 else 0.2)
    if s.subject == "text":
        size = min(W, H) * 0.14
    return cx, cy, size


def _shape_points(subject: str, r: float) -> list[tuple[float, float]]:
    if subject in ("ball", "dots"):
        return [(r * math.cos(2 * math.pi * k / 48), r * math.sin(2 * math.pi * k / 48)) for k in range(48)]
    if subject == "square":
        return [(-r, -r), (r, -r), (r, r), (-r, r)]
    if subject == "triangle":
        return [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (-90, 30, 150)]
    if subject == "diamond":
        return [(0, -r * 1.2), (r * 0.8, 0), (0, r * 1.2), (-r * 0.8, 0)]
    if subject == "star":
        return [((r if k % 2 == 0 else r * 0.45) * math.cos(math.radians(-90 + 36 * k)),
                 (r if k % 2 == 0 else r * 0.45) * math.sin(math.radians(-90 + 36 * k))) for k in range(10)]
    if subject == "heart":
        pts = []
        for k in range(60):
            a = 2 * math.pi * k / 60
            x = 16 * math.sin(a) ** 3
            y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a))
            pts.append((x * r / 16, y * r / 16))
        return pts
    return []


# stick figure skeleton (unit = size): (name, parent joint offset, length, rest angle)
def _stick_segments(d: dict, r: float) -> tuple[list[tuple[tuple[float, float], tuple[float, float]]], tuple[float, float], float]:
    """Forward kinematics in local coords (hip at origin). Returns bones, head centre, head radius."""
    lean = math.radians(d.get("lean", 0))
    torso = r * 0.55
    neck = (math.sin(lean) * torso, -math.cos(lean) * torso)
    bones = [((0.0, 0.0), neck)]

    def limb(start, a1, a2, l1, l2):
        a1r, a2r = math.radians(a1), math.radians(a1 + a2)
        j = (start[0] + math.sin(a1r) * l1, start[1] + math.cos(a1r) * l1)
        e = (j[0] + math.sin(a2r) * l2, j[1] + math.cos(a2r) * l2)
        return [(start, j), (j, e)]
    bones += limb((0.0, 0.0), d.get("thL", 0), -d.get("shL", 0), r * 0.4, r * 0.4)
    bones += limb((0.0, 0.0), d.get("thR", 0), -d.get("shR", 0), r * 0.4, r * 0.4)
    sh = (neck[0] * 0.85, neck[1] * 0.85)
    bones += limb(sh, d.get("arL", 0), d.get("foL", 0), r * 0.3, r * 0.3)
    bones += limb(sh, d.get("arR", 0), d.get("foR", 0), r * 0.3, r * 0.3)
    hr = r * 0.13
    head = (neck[0] + math.sin(lean) * hr * 1.1, neck[1] - hr * 1.1)
    return bones, head, hr


# ------------------------------------------------------------------------------------------- GIF frames

def frames(s: AnimSpec, fps: int = 20, scale: int = 1):
    from PIL import Image, ImageDraw, ImageFont
    n = max(8, min(72, round(s.duration * fps)))
    W, H = s.width * scale, s.height * scale
    col, bg = _rgb(s.color), _rgb(s.background)
    shadow_col = tuple(int(b * 0.55 + (0 if _lum(s.background) < 0.3 else -40)) for b in bg)
    font = None
    if s.subject == "text":
        for f in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
            try:
                font = ImageFont.truetype(f, int(_layout(s, 0)[2] * scale))
                break
            except OSError:
                continue
        font = font or ImageFont.load_default()
    out = []
    for k in range(n):
        t = k / n
        im = Image.new("RGB", (W, H), bg)
        dr = ImageDraw.Draw(im)
        for i in range(s.count):
            cx, cy, r = _layout(s, i)
            d = pose(s, i, t)
            ox, oy = (cx + d["dx"]) * scale, (cy + d["dy"]) * scale
            if d["shadow"] is not None and s.subject not in ("text",):
                gy = (cy + r * (1.05 if s.subject != "stickman" else 0.82)) * scale
                w = r * scale * (0.9 * d["shadow"] + 0.2)
                dr.ellipse([cx * scale + d["dx"] * scale - w, gy - w * 0.18, cx * scale + d["dx"] * scale + w, gy + w * 0.18], fill=shadow_col)
            a = math.radians(d["rot"])
            ca, sa = math.cos(a), math.sin(a)

            def tf(x, y):
                x, y = x * d["sx"], y * d["sy"]
                return (ox + (x * ca - y * sa) * scale, oy + (x * sa + y * ca) * scale)
            fill = tuple(int(c * d["op"] + b * (1 - d["op"])) for c, b in zip(col, bg))
            if s.subject == "stickman":
                bones, head, hr = _stick_segments(d, r)
                wdt = max(2, int(r * 0.06 * scale))
                for a0, a1 in bones:
                    dr.line([tf(*a0), tf(*a1)], fill=fill, width=wdt)
                    dr.ellipse([tf(*a1)[0] - wdt / 2, tf(*a1)[1] - wdt / 2, tf(*a1)[0] + wdt / 2, tf(*a1)[1] + wdt / 2], fill=fill)
                hx, hy = tf(*head)
                dr.ellipse([hx - hr * scale, hy - hr * scale, hx + hr * scale, hy + hr * scale], outline=fill, width=wdt)
            elif s.subject == "ring":
                pts = [tf(*p) for p in _shape_points("ball", r)]
                dr.line(pts + [pts[0]], fill=fill, width=max(3, int(r * 0.28 * scale)), joint="curve")
            elif s.subject == "spinner":
                for j in range(12):
                    ang = 2 * math.pi * j / 12
                    o = 0.15 + 0.85 * (j / 11)
                    c2 = tuple(int(c * o + b * (1 - o)) for c, b in zip(col, bg))
                    dr.line([tf(r * 0.55 * math.cos(ang), r * 0.55 * math.sin(ang)), tf(r * math.cos(ang), r * math.sin(ang))],
                            fill=c2, width=max(3, int(r * 0.16 * scale)))
            elif s.subject == "text":
                txt = Image.new("RGBA", (int(W * 0.9), int(r * 2.4 * scale)), (0, 0, 0, 0))
                td = ImageDraw.Draw(txt)
                bb = td.textbbox((0, 0), s.text, font=font)
                td.text(((txt.width - (bb[2] - bb[0])) / 2 - bb[0], (txt.height - (bb[3] - bb[1])) / 2 - bb[1]), s.text, font=font,
                        fill=fill + (255,))
                txt = txt.resize((max(1, int(txt.width * d["sx"])), max(1, int(txt.height * d["sy"]))))
                txt = txt.rotate(-d["rot"], expand=True)
                im.paste(txt, (int(ox - txt.width / 2), int(oy - txt.height / 2)), txt)
            else:
                dr.polygon([tf(*p) for p in _shape_points(s.subject, r)], fill=fill)
        out.append(im)
    return out, int(1000 * s.duration / n)


# ------------------------------------------------------------------------------------------- SVG + CSS

def _svg_shape(subject: str, r: float, color: str, s: AnimSpec) -> str:
    if subject in ("ball", "dots"):
        return f'<circle r="{r:.1f}" fill="{color}"/>'
    if subject == "ring":
        return f'<circle r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{r * 0.28:.1f}"/>'
    if subject == "spinner":
        return "".join(f'<line x1="{r * .55 * math.cos(2 * math.pi * j / 12):.1f}" y1="{r * .55 * math.sin(2 * math.pi * j / 12):.1f}" '
                       f'x2="{r * math.cos(2 * math.pi * j / 12):.1f}" y2="{r * math.sin(2 * math.pi * j / 12):.1f}" stroke="{color}" '
                       f'stroke-width="{r * .16:.1f}" stroke-linecap="round" opacity="{0.15 + 0.85 * j / 11:.2f}"/>' for j in range(12))
    if subject == "text":
        return (f'<text text-anchor="middle" dominant-baseline="central" font-family="system-ui,sans-serif" font-weight="800" '
                f'font-size="{r:.1f}" fill="{color}">{_esc(s.text)}</text>')
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in _shape_points(subject, r))
    return f'<polygon points="{pts}" fill="{color}"/>'


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def html(s: AnimSpec, steps: int = 40) -> str:
    """SVG + CSS keyframes sampled from pose(); stick figures are animated by redrawing their bones per keyframe
    via SVG <animate> on polyline points so the joints stay attached."""
    css, body = [], []
    dur = f"{s.duration:.2f}s"
    for i in range(s.count):
        cx, cy, r = _layout(s, i)
        ks = [pose(s, i, k / steps) for k in range(steps + 1)]
        kf = "\n".join(f"  {100 * k / steps:.1f}% {{ transform: translate({d['dx']:.1f}px,{d['dy']:.1f}px) rotate({d['rot']:.1f}deg) "
                       f"scale({d['sx']:.3f},{d['sy']:.3f}); opacity: {d['op']:.3f}; }}" for k, d in enumerate(ks))
        css.append(f"@keyframes a{i} {{\n{kf}\n}}\n.a{i} {{ animation: a{i} {dur} linear infinite; transform-origin: 0 0; }}")
        if ks[0]["shadow"] is not None:
            sk = "\n".join(f"  {100 * k / steps:.1f}% {{ transform: translate({d['dx']:.1f}px,0) scale({0.9 * d['shadow'] + 0.2:.3f},1); "
                           f"opacity: {0.25 + 0.35 * d['shadow']:.3f}; }}" for k, d in enumerate(ks))
            css.append(f"@keyframes s{i} {{\n{sk}\n}}\n.s{i} {{ animation: s{i} {dur} linear infinite; transform-origin: 0 0; }}")
            gy = r * (1.05 if s.subject != "stickman" else 0.82)
            body.append(f'<g transform="translate({cx:.1f},{cy + gy:.1f})"><ellipse class="s{i}" rx="{r:.1f}" ry="{r * 0.18:.1f}" fill="#000"/></g>')
        if s.subject == "stickman":
            frames_pts = []
            for d in ks:
                bones, head, hr = _stick_segments(d, r)
                frames_pts.append((bones, head))
            w = max(2, r * 0.06)
            parts = []
            for b in range(len(frames_pts[0][0])):
                vals = ";".join(f"{fp[0][b][0][0]:.1f},{fp[0][b][0][1]:.1f} {fp[0][b][1][0]:.1f},{fp[0][b][1][1]:.1f}" for fp in frames_pts)
                parts.append(f'<polyline fill="none" stroke="{s.color}" stroke-width="{w:.1f}" stroke-linecap="round">'
                             f'<animate attributeName="points" dur="{dur}" repeatCount="indefinite" values="{vals}"/></polyline>')
            hx = ";".join(f"{fp[1][0]:.1f}" for fp in frames_pts)
            hy = ";".join(f"{fp[1][1]:.1f}" for fp in frames_pts)
            parts.append(f'<circle r="{r * 0.13:.1f}" fill="none" stroke="{s.color}" stroke-width="{w:.1f}">'
                         f'<animate attributeName="cx" dur="{dur}" repeatCount="indefinite" values="{hx}"/>'
                         f'<animate attributeName="cy" dur="{dur}" repeatCount="indefinite" values="{hy}"/></circle>')
            shape = "".join(parts)
        else:
            shape = _svg_shape(s.subject, r, s.color, s)
        body.append(f'<g transform="translate({cx:.1f},{cy:.1f})"><g class="a{i}">{shape}</g></g>')
    ink = "#f5f5f5" if _lum(s.background) < 0.4 else "#1c1c1c"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(s.title)}</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:{s.background};color:{ink};font:15px system-ui,sans-serif}}
figure{{margin:0;width:min(96vw,{s.width * 2}px)}} svg{{width:100%;height:auto;display:block}}
figcaption{{display:flex;gap:10px;align-items:center;justify-content:center;padding:10px;opacity:.85}}
button{{font:inherit;color:inherit;background:transparent;border:1px solid currentColor;border-radius:8px;padding:6px 14px;min-height:36px;cursor:pointer}}
.paused *{{animation-play-state:paused!important}}
@media (prefers-reduced-motion: reduce){{svg:not(.play) *{{animation-play-state:paused!important}}}}
{chr(10).join(css)}
</style></head><body>
<figure><svg id="stage" viewBox="0 0 {s.width} {s.height}" role="img" aria-label="{_esc(s.title)}">
{chr(10).join(body)}
</svg><figcaption><button id="pp" aria-pressed="false">Pause</button><span>{s.duration:g}s loop · made by XON</span></figcaption></figure>
<script>
const st = document.getElementById('stage'), b = document.getElementById('pp');
b.onclick = () => {{ const p = st.classList.toggle('paused'); st.classList.add('play'); b.textContent = p ? 'Play' : 'Pause';
  b.setAttribute('aria-pressed', String(p)); p ? st.pauseAnimations() : st.unpauseAnimations(); }};
</script></body></html>
"""


def check(fr: list) -> dict:
    """Self-check: does it actually move, and does it stay on stage?"""
    import numpy as np
    a = [np.asarray(f, dtype=np.int16) for f in fr]
    diffs = [float(np.abs(a[k] - a[(k + 1) % len(a)]).mean()) for k in range(len(a))]
    bg = a[0][0, 0]
    edge = max(float(np.abs(f[[0, -1], :, :] - bg).max()) for f in a) if a else 0
    return {"frames": len(a), "moves": max(diffs) > 0.05, "mean_change": round(sum(diffs) / len(diffs), 3),
            "loop_seam": round(diffs[-1], 3), "touches_edge": edge > 60}


def render(spec: AnimSpec, out_base: str | Path) -> dict:
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    fr, ms = frames(spec)
    qc = check(fr)
    gif = out_base.with_suffix(".gif")
    fr[0].save(gif, save_all=True, append_images=fr[1:], duration=ms, loop=0, optimize=True)
    page = out_base.with_suffix(".html")
    page.write_text(html(spec))
    out_base.with_suffix(".json").write_text(json.dumps(spec.to_dict(), indent=1))
    return {"ok": True, "html": str(page), "gif": str(gif), "spec": spec.to_dict(), "check": qc}


def make(prompt: str, out_base: str | Path) -> dict:
    try:
        return render(parse(prompt), out_base)
    except Refused as e:
        return {"ok": False, "refused": True, "error": str(e)}
