"""Byte-level BPE tokenizer with FIM / file / tool special tokens and an HTML/CSS-aware pre-tokenizer."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SPECIAL_TOKENS = [
    "<|endoftext|>", "<|pad|>",
    "<|fim_prefix|>", "<|fim_middle|>", "<|fim_suffix|>",
    "<|file|>", "<|endfile|>",
    "<|user|>", "<|assistant|>", "<|tool|>", "<|tool_result|>",
    "<|image|>", "<|html|>", "<|css|>", "<|task|>", "<|test|>", "<|fix|>",
]

# Strings that are always one token: frequent HTML/CSS/Python units.
ATOMIC = [
    "    ", "        ", "\t", "\n\n",
    "<!DOCTYPE html>", "<div", "</div>", "<span", "</span>", "<button", "</button>", "<input", "<nav", "</nav>",
    "<section", "</section>", "<header", "</header>", "<footer", "</footer>", "<main", "</main>",
    "<table", "</table>", "<tr", "</tr>", "<td", "</td>", "<th", "</th>", "<ul", "</ul>", "<li", "</li>",
    "<a ", "</a>", "<img", "<p", "</p>", "<h1", "</h1>", "<h2", "</h2>", "<h3", "</h3>", "<form", "</form>",
    "<style>", "</style>", "<script", "</script>", "<svg", "</svg>", "<path", "<label", "</label>",
    ' class="', ' id="', ' style="', ' href="', ' src="', ' type="', ' alt="',
    "display:", "flex", "grid", "padding:", "margin:", "color:", "background:", "background-color:",
    "border:", "border-radius:", "font-size:", "font-weight:", "font-family:", "width:", "height:",
    "justify-content:", "align-items:", "gap:", "px;", "rem;", "em;", "%;",
    "def ", "return ", "class ", "import ", "from ", "self.", "if __name__", "assert ", "lambda ",
    "function ", "const ", "let ", "=> ", "console.log",
]

PRETOKEN = re.compile(
    r"""'(?:[sdmt]|ll|ve|re)| ?[A-Za-z_][A-Za-z0-9_]*| ?[0-9]{1,3}| ?[^\sA-Za-z0-9_]+|\s+(?!\S)|\s+""",
)


def _bytes_to_unicode() -> dict[int, str]:
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class BPETokenizer:
    def __init__(self, merges: list[tuple[int, int]] | None = None, atomic: list[str] | None = None,
                 specials: list[str] | None = None):
        self.merges = merges or []
        self.atomic = list(atomic if atomic is not None else ATOMIC)
        self.specials = list(specials if specials is not None else SPECIAL_TOKENS)
        self._build()

    # ---- vocab layout: 0..255 bytes | merges | atomic | specials
    def _build(self):
        self.vocab: dict[int, bytes] = {i: bytes([i]) for i in range(256)}
        self.ranks: dict[tuple[int, int], int] = {}
        for i, (a, b) in enumerate(self.merges):
            nid = 256 + i
            self.vocab[nid] = self.vocab[a] + self.vocab[b]
            self.ranks[(a, b)] = nid
        base = 256 + len(self.merges)
        self.atomic_ids = {s: base + i for i, s in enumerate(self.atomic)}
        for s, i in self.atomic_ids.items():
            self.vocab[i] = s.encode()
        base += len(self.atomic)
        self.special_ids = {s: base + i for i, s in enumerate(self.specials)}
        for s, i in self.special_ids.items():
            self.vocab[i] = s.encode()
        parts = [re.escape(s) for s in self.specials] + [re.escape(s) for s in sorted(self.atomic, key=len, reverse=True)]
        self._split = re.compile("(" + "|".join(parts) + ")") if parts else None
        self._cache: dict[str, list[int]] = {}

    @property
    def vocab_size(self) -> int:
        return 256 + len(self.merges) + len(self.atomic) + len(self.specials)

    def special(self, name: str) -> int:
        return self.special_ids[name]

    @property
    def eot(self) -> int:
        return self.special_ids["<|endoftext|>"]

    # ---- training
    @classmethod
    def train(cls, texts, vocab_size: int = 4096, min_freq: int = 2, verbose: bool = False) -> "BPETokenizer":
        tok = cls()
        n_merges = max(0, vocab_size - 256 - len(tok.atomic) - len(tok.specials))
        words: Counter = Counter()
        for t in texts:
            for chunk in tok._chunks(t):
                if chunk in tok.atomic_ids or chunk in tok.special_ids:
                    continue
                for w in PRETOKEN.findall(chunk):
                    words[w] += 1
        seqs = [list(w.encode()) for w in words]
        freqs = list(words.values())
        pair_counts: Counter = Counter()
        where: dict[tuple[int, int], set[int]] = defaultdict(set)
        for wi, s in enumerate(seqs):
            f = freqs[wi]
            for p in zip(s, s[1:]):
                pair_counts[p] += f
                where[p].add(wi)
        merges: list[tuple[int, int]] = []
        for m in range(n_merges):
            if not pair_counts:
                break
            best, cnt = max(pair_counts.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
            if cnt < min_freq:
                break
            nid = 256 + m
            merges.append(best)
            for wi in list(where.pop(best, ())):
                s, f = seqs[wi], freqs[wi]
                for p in zip(s, s[1:]):
                    pair_counts[p] -= f
                    if pair_counts[p] <= 0:
                        del pair_counts[p]
                ns, i = [], 0
                while i < len(s):
                    if i < len(s) - 1 and (s[i], s[i + 1]) == best:
                        ns.append(nid)
                        i += 2
                    else:
                        ns.append(s[i])
                        i += 1
                seqs[wi] = ns
                for p in zip(ns, ns[1:]):
                    pair_counts[p] += f
                    where[p].add(wi)
            pair_counts.pop(best, None)
            if verbose and m % 500 == 0:
                print(f"merge {m}/{n_merges} count={cnt}")
        return cls(merges, tok.atomic, tok.specials)

    def _chunks(self, text: str):
        if self._split is None:
            yield text
            return
        for c in self._split.split(text):
            if c:
                yield c

    def _encode_word(self, w: str) -> list[int]:
        hit = self._cache.get(w)
        if hit is not None:
            return hit
        s = list(w.encode())
        while len(s) > 1:
            best_rank, best_i = None, -1
            for i in range(len(s) - 1):
                r = self.ranks.get((s[i], s[i + 1]))
                if r is not None and (best_rank is None or r < best_rank):
                    best_rank, best_i = r, i
            if best_rank is None:
                break
            s = s[:best_i] + [best_rank] + s[best_i + 2:]
        if len(self._cache) < 500_000:
            self._cache[w] = s
        return s

    def encode(self, text: str, allow_special: bool = True) -> list[int]:
        out: list[int] = []
        for chunk in self._chunks(text):
            if allow_special and chunk in self.special_ids:
                out.append(self.special_ids[chunk])
            elif chunk in self.atomic_ids:
                out.append(self.atomic_ids[chunk])
            else:
                for w in PRETOKEN.findall(chunk):
                    out.extend(self._encode_word(w))
        return out

    def decode(self, ids, skip_special: bool = False) -> str:
        sp = set(self.special_ids.values())
        b = b"".join(self.vocab.get(i, b"") for i in ids if not (skip_special and i in sp))
        return b.decode("utf-8", errors="replace")

    def save(self, p: Path) -> None:
        Path(p).write_text(json.dumps({"type": "xon-bpe", "merges": self.merges, "atomic": self.atomic,
                                       "specials": self.specials}))

    @classmethod
    def load(cls, p: Path) -> "BPETokenizer":
        d = json.loads(Path(p).read_text())
        return cls([tuple(m) for m in d["merges"]], d["atomic"], d["specials"])
