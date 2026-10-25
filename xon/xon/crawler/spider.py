"""Polite crawler: robots.txt, crawl-delay, per-domain rate limits, backoff+demotion, resumable frontier."""
from __future__ import annotations

import hashlib
import heapq
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from xon import config
from xon.crawler.extract import BLOCKED_LICENSES, extract
from xon.crawler.robots import RobotsCache
from xon.workstation.governor import Governor, Halt

HERE = Path(__file__).parent
TEXT_TYPES = ("text/html", "text/plain", "text/css", "text/x-python", "application/javascript",
              "text/javascript", "image/svg+xml", "application/xhtml+xml")
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")
SOURCE_EXT = {".py": "python", ".js": "javascript", ".ts": "typescript", ".css": "css", ".html": "html",
              ".svg": "svg", ".md": "markdown"}


def load_yaml(name: str) -> dict:
    return yaml.safe_load((HERE / name).read_text())


class Domain:
    def __init__(self, name: str):
        self.name = name
        self.next_ok = 0.0
        self.errors = 0
        self.blocked = 0
        self.pages = 0
        self.demoted = False
        self.backoff = 0.0

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d):
        o = cls(d["name"])
        o.__dict__.update(d)
        return o


class Spider:
    def __init__(self, cfg: dict | None = None, out_dir: Path | None = None, gov: Governor | None = None,
                 allow: dict | None = None, seeds: list[dict] | None = None, state_path: Path | None = None,
                 delay_override: float | None = None):
        import requests
        self.cfg = cfg or config.load()
        self.ccfg = self.cfg["crawler"]
        self.gov = gov or Governor(self.cfg, "crawler")
        self.allow = allow if allow is not None else load_yaml("allowlist.yaml")
        self.seeds = seeds if seeds is not None else load_yaml("seeds.yaml")["seeds"]
        self.out = Path(out_dir or config.path(self.cfg, "data") / "raw")
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "img").mkdir(exist_ok=True)
        self.state_path = Path(state_path or self.out / "crawler_state.json")
        self.delay_override = delay_override
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.ccfg["user_agent"]
        self.robots = RobotsCache(self._fetch_text, self.ccfg["user_agent"])
        self.deny = [re.compile(p) for p in self.allow.get("deny_patterns", [])]
        self.frontier: list = []
        self.seen: set[str] = set()
        self.domains: dict[str, Domain] = {}
        self.img_meta: dict[str, dict] = {}
        self.stats = {"fetched": 0, "stored": 0, "images": 0, "skipped": {}, "errors": 0}
        self.log = config.log("crawler")
        self._load_state()
        if not self.frontier and not self.seen:
            for s in self.seeds:
                self.push(s["url"], s.get("priority", 5), s.get("category", "general"), 0)

    # ---- state
    def _load_state(self):
        if self.state_path.exists():
            s = json.loads(self.state_path.read_text())
            self.frontier = [tuple(x) for x in s["frontier"]]
            heapq.heapify(self.frontier)
            self.seen = set(s["seen"])
            self.domains = {k: Domain.from_dict(v) for k, v in s["domains"].items()}
            self.stats = s.get("stats", self.stats)
            self.img_meta = s.get("img_meta", {})

    def save_state(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"frontier": self.frontier, "seen": sorted(self.seen),
                                   "domains": {k: v.to_dict() for k, v in self.domains.items()}, "stats": self.stats,
                                   "img_meta": self.img_meta}))
        tmp.replace(self.state_path)

    # ---- policy
    def skip(self, reason: str):
        self.stats["skipped"][reason] = self.stats["skipped"].get(reason, 0) + 1

    def domain_rule(self, url: str) -> dict | None:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host in self.allow.get("deny_domains", []):
            return None
        rule = self.allow["allow"].get(host)
        if rule is None:
            return None
        if not any(parts.path.startswith(p) for p in rule.get("paths", ["/"])):
            return None
        return rule

    def permitted(self, url: str) -> str | None:
        """Return a skip reason, or None if the URL may be fetched."""
        if not url.startswith(("http://", "https://")):
            return "scheme"
        if any(d.search(url) for d in self.deny):
            return "denied_pattern"
        rule = self.domain_rule(url)
        if rule is None:
            return "not_allowlisted"
        d = self.dom(url)
        if d.blocked >= 2 or d.errors >= 6:
            return "domain_demoted"
        if d.pages >= rule.get("max_pages", 20):
            return "domain_page_cap"
        return None

    def dom(self, url: str) -> Domain:
        key = urlsplit(url).netloc
        if key not in self.domains:
            self.domains[key] = Domain(key)
        return self.domains[key]

    def push(self, url: str, priority: float, category: str, depth: int):
        h = hashlib.sha1(url.encode()).hexdigest()[:16]
        if h in self.seen:
            return
        self.seen.add(h)
        heapq.heappush(self.frontier, (priority + depth * 0.5, depth, url, category))

    # ---- fetching
    def _wait_domain(self, url: str, use_robots: bool = True):
        d = self.dom(url)
        delay = self.delay_override if self.delay_override is not None else self.ccfg["default_delay_s"]
        # robots.txt itself is fetched with use_robots=False (asking for its crawl-delay would recurse)
        cd = self.robots.crawl_delay(url) if (self.delay_override is None and use_robots) else None
        if cd is not None:
            delay = max(delay, cd)
        now = time.time()
        if d.next_ok > now:
            end = d.next_ok
            while time.time() < end:  # sleep in small steps so STOP is honored fast
                self.gov.tick()
                time.sleep(min(0.25, max(0, end - time.time())))
        d.next_ok = time.time() + delay + d.backoff

    def _get(self, url: str):
        if not self.gov.allow_request():
            raise Halt("request/bandwidth cap reached")
        r = self.session.get(url, timeout=self.ccfg["timeout_s"], stream=True, allow_redirects=True)
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > self.ccfg["max_bytes"]:
                break
        self.gov.add_bytes(len(body))
        return r, body

    def _fetch_text(self, url: str):
        self._wait_domain(url, use_robots=False)
        r, body = self._get(url)
        return r.status_code, body.decode(r.encoding or "utf-8", errors="replace")

    def _on_status(self, url: str, r) -> bool:
        d = self.dom(url)
        if r.status_code in (429, 503):
            ra = r.headers.get("Retry-After", "")
            wait = float(ra) if ra.isdigit() else max(2 * (d.backoff or 1.0), 1.0)
            d.backoff = min(600.0, wait)
            d.errors += 2
            d.demoted = True
            self.skip(f"http_{r.status_code}")
            self.log.warning(f"{r.status_code} from {d.name}: backing off {d.backoff:.0f}s, domain demoted")
            return False
        if r.status_code in (401, 403):
            d.blocked += 1
            d.demoted = True
            self.skip(f"http_{r.status_code}")
            return False
        if r.status_code >= 400:
            d.errors += 1
            self.skip(f"http_{r.status_code}")
            return False
        d.backoff = max(0.0, d.backoff / 2)
        return True

    # ---- main loop
    def run(self, max_pages: int | None = None, max_seconds: float | None = None) -> dict:
        max_pages = max_pages or self.ccfg["max_pages"]
        t0 = time.time()
        pages_f = open(self.out / "pages.jsonl", "a")
        n = 0
        try:
            while self.frontier and n < max_pages:
                self.gov.tick()
                if max_seconds and time.time() - t0 > max_seconds:
                    break
                _, depth, url, cat = heapq.heappop(self.frontier)
                why = self.permitted(url)
                if why:
                    self.skip(why)
                    continue
                if not self.robots.allowed(url):
                    self.skip("robots")
                    continue
                try:
                    self._wait_domain(url)
                    r, body = self._get(url)
                except Halt:
                    raise
                except Exception as e:
                    self.stats["errors"] += 1
                    self.dom(url).errors += 1
                    self.log.info(f"fetch error {url}: {str(e)[:120]}")
                    continue
                n += 1
                self.stats["fetched"] += 1
                if not self._on_status(url, r):
                    continue
                self.dom(url).pages += 1
                ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
                rec = self._handle(url, cat, depth, ctype, r, body)
                if rec:
                    pages_f.write(json.dumps(rec) + "\n")
                    pages_f.flush()
                    self.stats["stored"] += 1
                if n % 5 == 0:
                    self.save_state()
        finally:
            pages_f.close()
            self.save_state()
        self.stats["seconds"] = round(time.time() - t0, 1)
        return self.stats

    def _license_for(self, url: str, detected: str | None) -> str | None:
        rule = self.domain_rule(url) or {}
        path = urlsplit(url).path
        for prefix, lic in (rule.get("repo_licenses") or {}).items():
            if path.startswith(prefix):
                return detected if detected in BLOCKED_LICENSES else lic
        if detected:
            return detected
        lic = rule.get("license")
        return None if lic in (None, "detect") else lic

    def _handle(self, url, cat, depth, ctype, r, body) -> dict | None:
        ext = Path(urlsplit(url).path).suffix.lower()
        if ctype in IMAGE_TYPES:
            h = hashlib.sha1(body).hexdigest()
            p = self.out / "img" / f"{h}{ext or '.img'}"
            p.write_bytes(body)
            self.stats["images"] += 1
            meta = self.img_meta.get(url, {})
            return {"kind": "image_file", "url": url, "path": str(p.relative_to(self.out)), "category": cat,
                    "alt": meta.get("alt", ""), "caption": meta.get("caption", ""), "page": meta.get("page"),
                    "license": meta.get("license") or self._license_for(url, None)}
        if not any(ctype.startswith(t) for t in TEXT_TYPES) and ext not in SOURCE_EXT:
            self.skip("content_type")
            return None
        text = body.decode(r.encoding or "utf-8", errors="replace")
        if ctype in ("text/html", "application/xhtml+xml") and ext not in (".py", ".js", ".css", ".svg"):
            ex = extract(text, url)
            if ex["no_train"]:
                self.skip("no_train")
                return None
            lic = self._license_for(url, ex["license"])
            if lic in BLOCKED_LICENSES:
                self.skip("license_blocked")
                return None
            if not ex["noindex"]:
                for link in ex["links"]:
                    if self.permitted(link) is None:
                        self.push(link, 3 if cat == "general" else 1, cat, depth + 1)
            for im in ex["images"][:20]:
                if im["alt"] and self.permitted(im["src"]) is None:
                    self.img_meta[im["src"]] = {"alt": im["alt"], "caption": im["caption"], "page": url, "license": lic}
                    self.push(im["src"], 2, "image", depth + 1)
            return {"kind": "page", "url": url, "category": cat, "title": ex["title"], "text": ex["text"],
                    "code": ex["code"], "css": ex["css"], "svgs": ex["svgs"], "images": ex["images"],
                    "license": lic, "html": text[:200000], "fetched": time.time()}
        # raw source / css / svg file
        from xon.crawler.extract import detect_license
        lic = self._license_for(url, detect_license(text))
        if lic in BLOCKED_LICENSES:
            self.skip("license_blocked")
            return None
        lang = SOURCE_EXT.get(ext, "text")
        return {"kind": "source", "url": url, "category": cat, "lang": lang, "text": text, "license": lic,
                "fetched": time.time()}
