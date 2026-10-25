"""Image cleaning: decode/verify, size limits, perceptual-hash dedupe, unsafe and private-person filters."""
from __future__ import annotations

import base64
import io
import re

from PIL import Image

from xon.pipeline.clean_text import unsafe_reason

PERSON = re.compile(r"\b(person|people|man|woman|boy|girl|child|face|portrait|selfie|family|crowd)\b", re.I)


def ahash(img: Image.Image, n: int = 8) -> str:
    g = img.convert("L").resize((n, n), Image.BILINEAR)
    px = list(g.getdata())
    m = sum(px) / len(px)
    bits = "".join("1" if p > m else "0" for p in px)
    return "%016x" % int(bits, 2)


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    b = io.BytesIO()
    img.save(b, format=fmt, optimize=True)
    return base64.b64encode(b.getvalue()).decode()


def from_b64(s: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB")


def clean(data: bytes, caption: str, license: str | None, size: int = 64, people_licensed: bool = False):
    """Returns (record or None, status)."""
    if unsafe_reason(caption or ""):
        return None, "quarantine:unsafe_caption"
    if PERSON.search(caption or "") and not people_licensed:
        return None, "reject:private_person"
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None, "reject:decode"
    w, h = img.size
    if min(w, h) < 16:
        return None, "reject:too_small"
    if max(w, h) / min(w, h) > 4:
        return None, "reject:aspect"
    if not caption:
        return None, "reject:no_caption"
    img = img.resize((size, size), Image.BICUBIC)
    return {"image_b64": to_b64(img), "caption": caption, "ahash": ahash(img), "license": license}, "ok"


class PHashDeduper:
    def __init__(self, max_dist: int = 3):
        self.seen: list[str] = []
        self.max_dist = max_dist

    def add(self, h: str) -> bool:
        if any(hamming(h, s) <= self.max_dist for s in self.seen[-5000:]):
            return False
        self.seen.append(h)
        return True
