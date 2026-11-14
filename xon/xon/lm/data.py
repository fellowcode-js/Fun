"""LM data: records -> documents (code, HTML/CSS, instructions, FIM) -> token arrays."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np

from xon.tokenizer import BPETokenizer

FIM_RATE = 0.5


def fim(doc: str, rng: random.Random) -> str:
    if len(doc) < 20:
        return doc
    a, b = sorted(rng.sample(range(1, len(doc)), 2))
    pre, mid, suf = doc[:a], doc[a:b], doc[b:]
    return f"<|fim_prefix|>{pre}<|fim_suffix|>{suf}<|fim_middle|>{mid}"


def to_document(r: dict, rng: random.Random, fim_rate: float = FIM_RATE) -> str | None:
    k = r.get("kind")
    if k == "code":
        body = r["code"]
        if rng.random() < fim_rate:
            body = fim(body, rng)
        return f"<|file|>{(r.get('source') or '').split(':')[-1][-60:]}\n{body}<|endfile|>"
    if k == "text":
        return r["text"]
    if k == "ui":
        return f"<|task|>{r['description']}<|html|>{r['html']}"
    if k == "instruct":
        tests = f"<|test|>{r['tests']}\n" if r.get("tests") else ""
        return f"<|task|>{r['task']}\n{tests}<|assistant|>{r['code']}"
    if k == "fixpair":
        return f"<|fix|>{r['buggy']}<|test|>{r['tests']}\n<|assistant|>{r['fixed']}"
    return None


def is_heldout(r: dict, frac: float = 0.02) -> bool:
    """Deterministic held-out slice per source (by content hash)."""
    h = r.get("sha1") or hashlib.sha1((r.get("code") or r.get("text") or r.get("html") or "").encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF < frac


def build_tokenizer(records: list[dict], vocab_size: int, max_chars: int = 3_000_000, seed: int = 0) -> BPETokenizer:
    rng = random.Random(seed)
    texts, n = [], 0
    pool = records[:]
    rng.shuffle(pool)
    for r in pool:
        d = to_document(r, rng, fim_rate=0.0)
        if d:
            texts.append(d[:20000])
            n += len(texts[-1])
            if n > max_chars:
                break
    return BPETokenizer.train(texts, vocab_size=vocab_size)


def tokenize(records: list[dict], tok: BPETokenizer, seed: int = 0, repeat: dict | None = None, lang_repeat: dict | None = None):
    """Returns (train_ids, val_ids) as int32 arrays. `repeat` up-weights kinds, e.g. {'ui': 2}; `lang_repeat` up-weights
    code languages, e.g. {'python': 2, 'cpp': 2}."""
    rng = random.Random(seed)
    train, val = [], []
    for r in records:
        reps = (repeat or {}).get(r.get("kind"), 1)
        if r.get("kind") == "code":
            reps *= (lang_repeat or {}).get(r.get("lang"), 1)
        held = is_heldout(r)
        for _ in range(reps if not held else 1):
            d = to_document(r, rng)
            if not d:
                continue
            ids = tok.encode(d) + [tok.eot]
            (val if held else train).extend(ids)
    return np.array(train, dtype=np.int32), np.array(val, dtype=np.int32)


class Batcher:
    def __init__(self, ids: np.ndarray, seq_len: int, batch: int, seed: int = 0):
        self.ids, self.T, self.B = ids, seq_len, batch
        self.rng = np.random.default_rng(seed)

    def __call__(self):
        import torch
        n = len(self.ids) - self.T - 1
        idx = self.rng.integers(0, max(n, 1), self.B)
        x = np.stack([self.ids[i:i + self.T + 1] for i in idx]).astype(np.int64)
        x = torch.from_numpy(x)
        return x[:, :-1], x[:, 1:]


def save_ids(p: Path, ids: np.ndarray) -> None:
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    np.save(p, ids)


def load_ids(p: Path) -> np.ndarray:
    return np.load(p)
