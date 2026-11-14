"""Text cleaning: normalization, PII/secret scrubbing, unsafe-content quarantine, quality filters."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

PII_PATTERNS = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("SECRET", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
                          r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("SECRET", re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\b(\s*[:=]\s*)(['\"])[^'\"\s]{8,}\3")),
    ("PHONE", re.compile(r"(?<![\w])(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    ("ADDRESS", re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b\.?")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]

# Coarse keyword screen. It quarantines; it does not train. It is a floor, not a classifier.
UNSAFE = {
    "adult": re.compile(r"\b(porn\w*|xxx|nsfw|explicit sex|hentai|nude[sd]?|onlyfans)\b", re.I),
    "violence": re.compile(r"\b(gore|beheading|snuff|massacre video)\b", re.I),
    "illegal": re.compile(r"\b(buy cocaine|credit card dump|carding forum|child sexual)\b", re.I),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def scrub_pii(text: str) -> tuple[str, dict]:
    counts: Counter = Counter()
    for tag, pat in PII_PATTERNS:
        def repl(m, tag=tag):
            counts[tag] += 1
            if tag == "SECRET" and m.lastindex and m.lastindex >= 3:
                return f"{m.group(1)}{m.group(2)}{m.group(3)}<SECRET>{m.group(3)}"
            return f"<{tag}>"
        text = pat.sub(repl, text)
    return text, dict(counts)


def unsafe_reason(text: str) -> str | None:
    for name, pat in UNSAFE.items():
        if len(pat.findall(text)) >= 1:
            return f"unsafe_{name}"
    return None


def quality_reason(text: str, min_chars: int = 80) -> str | None:
    if len(text) < min_chars:
        return "too_short"
    letters = sum(c.isalpha() for c in text)
    if letters / max(len(text), 1) < 0.35:
        return "low_alpha"
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        top = Counter(lines).most_common(1)[0][1]
        if len(lines) > 5 and top / len(lines) > 0.4:
            return "repetitive"
    words = text.split()
    if words and len(set(words)) / len(words) < 0.15 and len(words) > 50:
        return "repetitive"
    return None


def clean(text: str, min_chars: int = 80) -> tuple[str | None, str, dict]:
    """Returns (clean_text or None, status, pii_counts). status is 'ok', 'quarantine:<why>' or 'reject:<why>'."""
    t = normalize(text)
    u = unsafe_reason(t)
    if u:
        return None, f"quarantine:{u}", {}
    t, pii = scrub_pii(t)
    q = quality_reason(t, min_chars)
    if q:
        return None, f"reject:{q}", pii
    return t, "ok", pii
