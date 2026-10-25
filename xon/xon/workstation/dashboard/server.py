"""Local dashboard: crawl stats, rejects, disk/bandwidth, image grid, loss curves, eval history, nodes, STOP."""
from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from xon import config
from xon.config import jsonl_read

HERE = Path(__file__).parent


def gather(cfg: dict) -> dict:
    from xon.nodes.common import nodes
    from xon.workstation.governor import Governor
    ex = config.path(cfg, "exchange")
    ck = config.path(cfg, "checkpoints")
    data = config.path(cfg, "data")
    logs = config.path(cfg, "logs")
    man = {}
    p = ex / "shards" / "manifest.json"
    if p.exists():
        man = json.loads(p.read_text())
    kinds, lic = {}, {}
    for s in man.get("shards", []):
        for k, v in s["kinds"].items():
            kinds[k] = kinds.get(k, 0) + v
        for k, v in s["licenses"].items():
            lic[k] = lic.get(k, 0) + v
    crawl = jsonl_read(ex / "crawl_stats.jsonl")
    rejects, pages, fetched = {}, 0, 0
    for c in crawl:
        for k, v in (c.get("clean") or {}).items():
            if k.startswith(("reject", "quarantine")):
                rejects[k] = rejects.get(k, 0) + v
        for k, v in ((c.get("crawl") or {}).get("skipped") or {}).items():
            rejects[f"skip:{k}"] = rejects.get(f"skip:{k}", 0) + v
        fetched += (c.get("crawl") or {}).get("fetched", 0)
        pages += (c.get("crawl") or {}).get("stored", 0)
    hist = [json.loads(l) for l in (ck / "history.jsonl").read_text().splitlines()] if (ck / "history.jsonl").exists() else []
    promoted = json.loads((ck / "promoted" / "metrics.json").read_text()) if (ck / "promoted" / "metrics.json").exists() else None
    lm_log = [r for r in jsonl_read(logs / "lm_train.jsonl") if "loss" in r][-400:]
    lm_val = [r for r in jsonl_read(logs / "lm_train.jsonl") if "val_loss" in r][-100:]
    v_log = [r for r in jsonl_read(logs / "vision_train.jsonl") if "loss" in r][-400:]
    status = json.loads((ex / "status.json").read_text()) if (ex / "status.json").exists() else {}
    images = sorted((data / "synth").glob("cycle-*/*.png"))[-6:]
    gallery = []
    for f in images:
        gallery.append({"src": f"/img?p={f.relative_to(data)}", "caption": f.stem})
    web = sorted((data / "raw_live" / "img").glob("*"))[-4:] + sorted((data / "raw_mock" / "img").glob("*"))[-6:]
    caps = {}
    for raw in ("raw_live", "raw_mock"):
        for r in jsonl_read(data / raw / "pages.jsonl")[-400:]:
            if r.get("kind") == "image_file":
                caps[Path(r["path"]).name] = r.get("caption") or r.get("alt") or ""
    for f in web:
        gallery.append({"src": f"/img?p={f.relative_to(data)}", "caption": caps.get(f.name, f.name[:10]), "web": True})
    return {"governor": Governor(cfg).usage(), "kinds": kinds, "licenses": lic, "rejects": rejects,
            "pages_fetched": fetched, "pages_stored": pages, "shards": len(man.get("shards", [])),
            "history": [{"cycle": h["cycle"], "promoted": h["promoted"], "reason": h["reason"], "metrics": h["metrics"],
                         "minutes": h.get("minutes")} for h in hist],
            "promoted": promoted, "lm_log": lm_log, "lm_val": lm_val, "vision_log": v_log, "status": status,
            "nodes": nodes(cfg), "gallery": gallery, "tier": cfg["xon"]["tier"]}


def make_handler(cfg: dict):
    data_dir = config.path(cfg, "data")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, "text/html; charset=utf-8", (HERE / "index.html").read_bytes())
            if self.path.startswith("/api/status"):
                return self._send(200, "application/json", json.dumps(gather(cfg), default=str).encode())
            if self.path.startswith("/img?p="):
                from urllib.parse import unquote
                rel = unquote(self.path.split("=", 1)[1])
                f = (data_dir / rel).resolve()
                if data_dir.resolve() not in f.parents or not f.exists():
                    return self._send(404, "text/plain", b"no")
                ctype = "image/png" if f.suffix == ".png" else "image/svg+xml" if f.suffix == ".svg" else "application/octet-stream"
                return self._send(200, ctype, f.read_bytes())
            return self._send(404, "text/plain", b"not found")

        def do_POST(self):
            if self.path == "/api/stop":
                from xon.workstation.governor import Governor
                Governor(cfg).stop("dashboard STOP button")
                return self._send(200, "application/json", b'{"stopped": true}')
            if self.path == "/api/resume":
                from xon.workstation.governor import Governor
                Governor(cfg).clear_stop()
                return self._send(200, "application/json", b'{"stopped": false}')
            return self._send(404, "text/plain", b"not found")

    return H


def serve(cfg: dict, port: int = 8787, background: bool = False):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg))
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    print(f"XON dashboard at http://127.0.0.1:{srv.server_address[1]}/")
    srv.serve_forever()
