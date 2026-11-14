"""Fetch a URL following the crawler's rules: robots.txt, honest UA, deny patterns, governor caps."""
from xon.crawler.extract import extract

SPEC = {"name": "web_fetch", "description": "Fetch a web page (robots.txt respected) and return its text.",
        "params": {"url": "str"}}


def run(ctx, url: str) -> dict:
    from xon.crawler.spider import Spider
    allow = {"allow": {}, "deny_patterns": Spider(ctx.cfg, out_dir=ctx.root / ".xon" / "fetch", seeds=[],
                                                  allow={"allow": {}, "deny_patterns": []}).allow.get("deny_patterns", [])}
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    allow["allow"][host] = {"license": "detect", "paths": ["/"], "max_pages": 50}
    from xon.crawler.spider import load_yaml
    allow["deny_patterns"] = load_yaml("allowlist.yaml").get("deny_patterns", [])
    sp = Spider(ctx.cfg, out_dir=ctx.root / ".xon" / "fetch", seeds=[], allow=allow,
                state_path=ctx.root / ".xon" / "fetch" / "state.json")
    why = sp.permitted(url)
    if why:
        return {"ok": False, "error": f"blocked: {why}"}
    if not sp.robots.allowed(url):
        return {"ok": False, "error": "disallowed by robots.txt"}
    sp._wait_domain(url)
    r, body = sp._get(url)
    text = body.decode(r.encoding or "utf-8", errors="replace")
    if "html" in r.headers.get("Content-Type", ""):
        ex = extract(text, url)
        return {"ok": r.status_code < 400, "status": r.status_code, "title": ex["title"], "text": ex["text"][:20000],
                "license": ex["license"], "links": ex["links"][:50]}
    return {"ok": r.status_code < 400, "status": r.status_code, "text": text[:20000]}
