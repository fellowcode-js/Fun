"""Open-dataset seeders with license checks. Write cleaned records straight into shards."""
from __future__ import annotations

import sys
import sysconfig
import time
from pathlib import Path

import yaml

from xon import config
from xon.pipeline import clean_code
from xon.pipeline.store import EvalGuard, ShardWriter

HERE = Path(__file__).parent
API = "https://datasets-server.huggingface.co/rows"
LANG = {"Python": "python", "JavaScript": "javascript", "TypeScript": "typescript", "HTML": "html", "CSS": "css"}


def sources() -> dict:
    return yaml.safe_load((HERE / "licenses.yaml").read_text())["sources"]


def fetch_stdlib(w: ShardWriter, max_files: int = 400, max_bytes: int = 6_000_000, gov=None) -> dict:
    src = Path(sysconfig.get_paths()["stdlib"])
    files = sorted(p for p in src.glob("*.py") if not p.name.startswith("_"))
    files += sorted(p for p in src.glob("*/*.py") if "test" not in p.parts and "idlelib" not in p.parts)
    n = total = 0
    dd = clean_code.MinHashDeduper()
    for p in files:
        if n >= max_files or total >= max_bytes:
            break
        if gov:
            gov.tick()
        try:
            code = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        code, _ = clean_code.scrub_secrets(code)
        if clean_code.reject_reason(code, "python", "PSF-2.0") or not dd.add(code):
            continue
        if w.add({"kind": "code", "code": code, "lang": "python", "license": "PSF-2.0",
                  "source": f"python-stdlib:{p.relative_to(src)}"}):
            n += 1
            total += len(code)
    return {"files": n, "bytes": total}


def _rows(dataset: str, cfg: str, split: str, offset: int, length: int = 100, timeout: int = 30) -> list[dict]:
    import requests
    r = requests.get(API, params={"dataset": dataset, "config": cfg, "split": split, "offset": offset, "length": length},
                     timeout=timeout, headers={"User-Agent": "XON-fetch_open/0.1"})
    r.raise_for_status()
    return [x["row"] for x in r.json().get("rows", [])]


def fetch_github_code(w: ShardWriter, max_rows: int = 600, max_bytes: int = 4_000_000, gov=None, delay: float = 1.0) -> dict:
    s = sources()["github_code_clean"]
    allow = set(s["allow_row_licenses"])
    kept = seen = total = 0
    lic_skip = 0
    offset = 0
    while seen < max_rows and total < max_bytes:
        if gov:
            gov.tick()
            if not gov.allow_request():
                break
        rows = _rows(s["dataset"], s["config"], s["split"], offset)
        if not rows:
            break
        if gov:
            gov.add_bytes(sum(len(r.get("code", "")) for r in rows))
        offset += len(rows)
        for r in rows:
            seen += 1
            if r["license"] not in allow:
                lic_skip += 1
                continue
            if r["language"] not in s["languages"]:
                continue
            code, _ = clean_code.scrub_secrets(r["code"])
            lic = r["license"].upper().replace("APACHE-2.0", "Apache-2.0").replace("CC0-1.0", "CC0-1.0")
            lic = {"MIT": "MIT", "BSD-3-CLAUSE": "BSD-3-Clause", "BSD-2-CLAUSE": "BSD-2-Clause", "ISC": "ISC",
                   "UNLICENSE": "Unlicense"}.get(lic, lic)
            if clean_code.reject_reason(code, LANG[r["language"]], lic):
                continue
            if w.add({"kind": "code", "code": code, "lang": LANG[r["language"]], "license": lic,
                      "source": f"hf:{s['dataset']}:{r['repo_name']}/{r['path']}"}):
                kept += 1
                total += len(code)
        time.sleep(delay)
    return {"seen": seen, "kept": kept, "bytes": total, "license_skipped": lic_skip}


def fetch_mbpp(w: ShardWriter, gov=None) -> dict:
    s = sources()["mbpp"]
    kept = 0
    for off in range(0, 400, 100):
        if gov:
            gov.tick()
        rows = _rows(s["dataset"], s["config"], s["split"], off)
        if not rows:
            break
        for r in rows:
            tests = "\n".join(r.get("test_list", []))
            if w.add({"kind": "instruct", "task": r["prompt"], "code": r["code"], "tests": tests,
                      "license": "CC-BY-4.0", "source": f"hf:{s['dataset']}:{r['task_id']}"}):
                kept += 1
        time.sleep(0.5)
    return {"kept": kept}


def run(cfg: dict | None = None, shard_dir: Path | None = None, online: bool = True, gov=None,
        max_rows: int = 600) -> dict:
    cfg = cfg or config.load()
    shard_dir = shard_dir or config.path(cfg, "exchange") / "shards"
    guard = EvalGuard(config.path(cfg, "evalsets"))
    out = {}
    w = ShardWriter(shard_dir, "open", guard=guard)
    out["python_stdlib"] = fetch_stdlib(w, gov=gov)
    if online:
        for name, fn in (("github_code_clean", lambda: fetch_github_code(w, max_rows=max_rows, gov=gov)),
                         ("mbpp", lambda: fetch_mbpp(w, gov=gov))):
            try:
                out[name] = fn()
            except Exception as e:
                out[name] = {"error": str(e)[:200]}
    w.close()
    out["dropped_eval_collisions"] = w.dropped_eval
    out["shards"] = w.written
    return out


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(run(online="--offline" not in sys.argv), indent=1))
