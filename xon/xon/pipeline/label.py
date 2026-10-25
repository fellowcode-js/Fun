"""Labels: weak labels parsed from captions, and confidence-thresholded pseudo-labels from the vision net."""
from __future__ import annotations

import re

from xon.datasets.shapes import COLORS, SHAPES


def caption_labels(caption: str, classes: list[str] = SHAPES) -> list[str]:
    words = set(re.findall(r"[a-z]+", caption.lower()))
    return [c for c in classes if c in words]


def weak_label(caption: str) -> dict:
    labs = caption_labels(caption)
    cols = [c for c in COLORS if re.search(rf"\b{c}\b", caption.lower())]
    return {"class": labs[0] if len(labs) == 1 else None, "color": cols[0] if len(cols) == 1 else None,
            "source": "caption" if len(labs) == 1 else None}


def pseudo_label(probs, classes: list[str], threshold: float = 0.8) -> dict | None:
    """probs: 1-D sequence of class probabilities. Returns a label only above the confidence threshold."""
    best = max(range(len(probs)), key=lambda i: probs[i])
    p = float(probs[best])
    if p < threshold:
        return None
    return {"class": classes[best], "confidence": round(p, 4), "source": "pseudo"}
