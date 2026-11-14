"""BM25 search over XON's crawled + open-dataset shards (docs, code). Grounds answers in licensed sources."""
import math
import re
from collections import Counter

SPEC = {"name": "docs_search", "description": "Search crawled docs and permissively licensed code (BM25). "
        "kind: any|code|text; lang filter e.g. python, cpp.", "params": {"query": "str", "kind": "str?", "lang": "str?", "k": "int?"}}
_INDEX: dict = {}


def _tok(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z_][a-z0-9_]+", s.lower()) if len(t) > 1]


def _build(ctx):
    from xon import config
    from xon.pipeline.store import iter_records
    key = str(config.path(ctx.cfg, "exchange"))
    if key in _INDEX:
        return _INDEX[key]
    docs = []
    for r in iter_records(config.path(ctx.cfg, "exchange") / "shards", kinds={"code", "text", "instruct"}):
        body = r.get("code") or r.get("text") or ""
        if r.get("kind") == "instruct":
            body = r.get("task", "") + "\n" + r.get("code", "")
        docs.append({"text": body, "source": r.get("source"), "license": r.get("license"), "kind": r.get("kind"), "lang": r.get("lang"),
                     "tf": Counter(_tok(body[:20000]))})
    df = Counter()
    for d in docs:
        df.update(d["tf"].keys())
    avg = sum(sum(d["tf"].values()) for d in docs) / max(len(docs), 1)
    _INDEX[key] = (docs, df, avg)
    return _INDEX[key]


def run(ctx, query: str, kind: str = "any", lang: str = "", k: int = 5) -> dict:
    docs, df, avg = _build(ctx)
    q = _tok(query)
    N = len(docs)
    scored = []
    for d in docs:
        if kind != "any" and d["kind"] != kind:
            continue
        if lang and (d["lang"] or "") != lang:
            continue
        L = sum(d["tf"].values()) or 1
        s = 0.0
        for t in q:
            f = d["tf"].get(t, 0)
            if f:
                idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * L / avg))
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    hits = []
    for s, d in scored[:k]:
        text = d["text"]
        pos = min((text.lower().find(t) for t in q if text.lower().find(t) >= 0), default=0)
        hits.append({"score": round(s, 2), "source": d["source"], "license": d["license"], "kind": d["kind"],
                     "snippet": text[max(0, pos - 200):pos + 600]})
    return {"ok": True, "hits": hits, "searched": N}
