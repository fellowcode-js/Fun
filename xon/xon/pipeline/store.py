"""Shard storage: gzip JSONL shards + manifest with hashes and licenses; eval-set dedupe guard."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_hash(rec: dict) -> str:
    key = rec.get("code") or rec.get("text") or rec.get("html") or rec.get("image_b64") or json.dumps(rec, sort_keys=True)
    import re
    return hashlib.sha1(re.sub(r"\s+", " ", key).strip().encode()).hexdigest()


class Manifest:
    def __init__(self, d: Path):
        self.dir = Path(d)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "manifest.json"

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return {"shards": []}

    def add(self, entry: dict) -> None:
        m = self.load()
        m["shards"] = [s for s in m["shards"] if s["name"] != entry["name"]] + [entry]
        m["updated"] = time.time()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=1))
        os.replace(tmp, self.path)

    def remove(self, name: str) -> None:
        m = self.load()
        m["shards"] = [s for s in m["shards"] if s["name"] != name]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=1))
        os.replace(tmp, self.path)

    def digest(self) -> str:
        m = self.load()
        return hashlib.sha256("".join(sorted(s["sha256"] for s in m["shards"])).encode()).hexdigest()[:16]


class ShardWriter:
    def __init__(self, d: Path, prefix: str, max_records: int = 2000, guard: "EvalGuard | None" = None):
        self.dir = Path(d)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prefix, self.max = prefix, max_records
        self.manifest = Manifest(self.dir)
        self.guard = guard
        self.buf: list[dict] = []
        self.written: list[str] = []
        self.dropped_eval = 0
        self._seen: set[str] = set()

    def add(self, rec: dict) -> bool:
        h = rec.setdefault("sha1", content_hash(rec))
        if h in self._seen:
            return False
        if self.guard and self.guard.collides(rec):
            self.dropped_eval += 1
            return False
        self._seen.add(h)
        self.buf.append(rec)
        if len(self.buf) >= self.max:
            self.flush()
        return True

    def flush(self) -> str | None:
        if not self.buf:
            return None
        name = f"{self.prefix}-{int(time.time() * 1000)}-{len(self.written):03d}.jsonl.gz"
        tmp = self.dir / (name + ".part")
        with gzip.open(tmp, "wt") as f:
            for r in self.buf:
                f.write(json.dumps(r) + "\n")
        final = self.dir / name
        os.replace(tmp, final)  # atomic: readers never see half a shard
        kinds = Counter(r.get("kind", "?") for r in self.buf)
        lic = Counter(r.get("license") or "unknown" for r in self.buf)
        self.manifest.add({"name": name, "n": len(self.buf), "kinds": dict(kinds), "licenses": dict(lic),
                           "sha256": sha256_file(final), "bytes": final.stat().st_size, "created": time.time(),
                           "sources": sorted({(r.get("source") or "")[:60] for r in self.buf})[:20]})
        self.written.append(name)
        self.buf = []
        return name

    def close(self) -> list[str]:
        self.flush()
        return self.written


def read_shard(p: Path):
    with gzip.open(p, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def iter_records(d: Path, kinds: set[str] | None = None, names: list[str] | None = None):
    m = Manifest(d).load()
    for s in m["shards"]:
        if names is not None and s["name"] not in names:
            continue
        if kinds and not (set(s["kinds"]) & kinds):
            continue
        p = Path(d) / s["name"]
        if not p.exists():
            continue
        for r in read_shard(p):
            if kinds is None or r.get("kind") in kinds:
                yield r


class EvalGuard:
    """Hashes of every frozen eval item; training records that collide are dropped (anti-contamination)."""

    def __init__(self, evalsets: Path):
        self.hashes: set[str] = set()
        import re
        for p in Path(evalsets).glob("**/*.jsonl"):
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                for k in ("prompt", "solution", "code", "html", "text", "buggy", "fixed"):
                    v = r.get(k)
                    if isinstance(v, str) and len(v) > 30:
                        self.hashes.add(hashlib.sha1(re.sub(r"\s+", " ", v).strip().encode()).hexdigest())
                if r.get("sha1"):
                    self.hashes.add(r["sha1"])

    def collides(self, rec: dict) -> bool:
        import re
        for k in ("code", "text", "html", "prompt"):
            v = rec.get(k)
            if isinstance(v, str) and hashlib.sha1(re.sub(r"\s+", " ", v).strip().encode()).hexdigest() in self.hashes:
                return True
        return False


def prune_cold(d: Path, keep_names: set[str], target_bytes: int) -> list[str]:
    """Pruning policy: delete oldest shards that are not in the replay buffer / keep set until under target."""
    man = Manifest(d)
    m = man.load()
    total = sum(s["bytes"] for s in m["shards"])
    removed = []
    for s in sorted(m["shards"], key=lambda s: s["created"]):
        if total <= target_bytes:
            break
        if s["name"] in keep_names:
            continue
        (Path(d) / s["name"]).unlink(missing_ok=True)
        man.remove(s["name"])
        total -= s["bytes"]
        removed.append(s["name"])
    return removed
