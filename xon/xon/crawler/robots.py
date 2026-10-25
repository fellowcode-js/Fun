"""robots.txt handling with crawl-delay, cached per domain."""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlsplit


class RobotsCache:
    def __init__(self, fetch, user_agent: str, ttl_s: float = 3600):
        """fetch(url) -> (status, text). Injected so the governor/rate limits apply to robots fetches too."""
        self.fetch, self.ua, self.ttl = fetch, user_agent, ttl_s
        self._cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser | None, str]] = {}

    def _get(self, url: str):
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit
        rp = urllib.robotparser.RobotFileParser()
        try:
            status, text = self.fetch(key + "/robots.txt")
        except Exception:
            status, text = 599, ""
        if status in (401, 403):
            mode = "deny"  # per RFC 9309: treat as fully disallowed
            rp = None
        elif status >= 500:
            mode = "deny"  # server error: be conservative, retry after ttl
            rp = None
        elif status >= 400:
            mode = "allow"  # no robots.txt
            rp = None
        else:
            rp.parse(text.splitlines())
            rp._xon_delay = self._parse_delay(text)  # stdlib only accepts integer delays
            mode = "parsed"
        hit = (time.time(), rp, mode)
        self._cache[key] = hit
        return hit

    def _parse_delay(self, text: str) -> float | None:
        agents, delay_for, in_rules = [], {}, False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if in_rules:  # a new group starts
                    agents, in_rules = [], False
                agents.append(v.lower())
            elif k == "crawl-delay":
                in_rules = True
                try:
                    for a in agents or ["*"]:
                        delay_for.setdefault(a, float(v))
                except ValueError:
                    pass
            elif k in ("allow", "disallow"):
                in_rules = True
        me = self.ua.split("/")[0].lower()
        for a, d in delay_for.items():
            if a != "*" and a in me:
                return d
        return delay_for.get("*")

    def allowed(self, url: str) -> bool:
        _, rp, mode = self._get(url)
        if mode == "deny":
            return False
        if rp is None:
            return True
        return rp.can_fetch(self.ua, url)

    def crawl_delay(self, url: str) -> float | None:
        _, rp, _ = self._get(url)
        if rp is None:
            return None
        d = getattr(rp, "_xon_delay", None)
        if d is None:
            d = rp.crawl_delay(self.ua)
        if d is None:
            rr = rp.request_rate(self.ua)
            if rr:
                d = rr.seconds / max(rr.requests, 1)
        return float(d) if d is not None else None
