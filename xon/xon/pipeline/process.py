"""Raw crawl -> cleaned, filtered, labeled records in shards. Shared by the crawler node and `xon crawl`."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from xon.pipeline import clean_code, clean_images, clean_text, label
from xon.pipeline.store import EvalGuard, ShardWriter


def process_raw(raw_dir: Path, shard_dir: Path, evalsets: Path, quarantine_dir: Path | None = None,
                offset_file: Path | None = None) -> dict:
    raw_dir, shard_dir = Path(raw_dir), Path(shard_dir)
    pages = raw_dir / "pages.jsonl"
    stats: Counter = Counter()
    if not pages.exists():
        return dict(stats)
    offset_file = offset_file or raw_dir / "processed.offset"
    start = int(offset_file.read_text()) if offset_file.exists() else 0
    w = ShardWriter(shard_dir, "crawl", guard=EvalGuard(evalsets))
    dd = clean_code.MinHashDeduper()
    ph = clean_images.PHashDeduper()
    quarantine = (quarantine_dir or raw_dir / "quarantine")
    quarantine.mkdir(parents=True, exist_ok=True)
    qf = open(quarantine / "quarantine.jsonl", "a")
    lines = pages.read_text().splitlines()
    for line in lines[start:]:
        if not line.strip():
            continue
        r = json.loads(line)
        lic = r.get("license")
        if r["kind"] == "page":
            t, status, pii = clean_text.clean(r.get("text", ""))
            for k, v in pii.items():
                stats[f"pii_{k}"] += v
            if status.startswith("quarantine"):
                qf.write(json.dumps({"url": r["url"], "status": status}) + "\n")
                stats[status] += 1
                continue
            if t:
                if dd.add(t):
                    w.add({"kind": "text", "text": t, "source": r["url"], "license": lic, "category": r["category"]})
                    stats["text"] += 1
                else:
                    stats["reject:near_dup"] += 1
            else:
                stats[status] += 1
            for block in r.get("code", []):
                code, _ = clean_code.scrub_secrets(block)
                why = clean_code.reject_reason(code, "python", lic if lic else None)
                if why:
                    stats[f"reject:code_{why.split(':')[0]}"] += 1
                    continue
                if dd.add(code):
                    w.add({"kind": "code", "code": code, "lang": "python" if clean_code.python_ok(code) else "snippet",
                           "source": r["url"], "license": lic})
                    stats["code"] += 1
            if r.get("css", "").strip():
                css, _ = clean_code.scrub_secrets(r["css"])
                if len(css) > 40 and dd.add(css):
                    w.add({"kind": "code", "code": css, "lang": "css", "source": r["url"], "license": lic})
                    stats["css"] += 1
            for svg in r.get("svgs", []):
                if 40 < len(svg) < 20000 and dd.add(svg):
                    w.add({"kind": "code", "code": svg, "lang": "svg", "source": r["url"], "license": lic})
                    stats["svg"] += 1
        elif r["kind"] == "source":
            code, n_sec = clean_code.scrub_secrets(r["text"])
            stats["secrets_scrubbed"] += n_sec
            why = clean_code.reject_reason(code, r["lang"], lic)
            if why:
                stats[f"reject:{why.split(':')[0]}"] += 1
                continue
            if dd.add(code):
                w.add({"kind": "code", "code": code, "lang": r["lang"], "source": r["url"], "license": lic})
                stats["code"] += 1
            else:
                stats["reject:near_dup"] += 1
        elif r["kind"] == "image_file":
            p = raw_dir / r["path"]
            if not p.exists():
                continue
            cap = r.get("caption") or r.get("alt") or ""
            rec, status = clean_images.clean(p.read_bytes(), cap, lic)
            if rec is None:
                stats[status] += 1
                if status.startswith("quarantine"):
                    qf.write(json.dumps({"url": r["url"], "status": status}) + "\n")
                continue
            if not ph.add(rec["ahash"]):
                stats["reject:image_dup"] += 1
                continue
            rec.update({"kind": "image", "source": r["url"], **{"weak": label.weak_label(cap)}})
            w.add(rec)
            stats["image"] += 1
    qf.close()
    w.close()
    offset_file.write_text(str(len(lines)))
    stats["dropped_eval_collisions"] = w.dropped_eval
    stats["shards"] = len(w.written)
    return dict(stats)
