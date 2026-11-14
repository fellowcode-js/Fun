import json

from xon.crawler.extract import detect_license, extract
from xon.crawler.mockweb import MockWeb, mock_allowlist
from xon.crawler.spider import Spider


def run_spider(cfg, m, **kw):
    sp = Spider(cfg, allow=mock_allowlist(), seeds=m.seeds(), delay_override=0.01, **kw)
    return sp, sp.run(max_pages=kw.pop("max_pages", 100) if "max_pages" in kw else 100)


def test_polite_crawl_rules(home):
    with MockWeb() as m:
        sp, st = run_spider(home, m)
        hits = m.hits("a")
        assert not any(h.startswith("/private") for h in hits), "robots.txt Disallow ignored"
        assert "/login" not in hits, "deny pattern ignored"
        assert hits[0] == "/robots.txt"
        assert st["skipped"].get("http_429", 0) >= 1 and st["skipped"].get("http_403", 0) >= 1
        assert len(m.hits("403")) <= 3, "kept hammering a 403 domain"
        assert st["skipped"].get("no_train") == 1
        assert st["skipped"].get("license_blocked") == 1
        d429 = sp.dom(m.url("429"))
        assert d429.demoted and d429.backoff >= 1


def test_resume_from_state(home):
    with MockWeb() as m:
        sp = Spider(home, allow=mock_allowlist(), seeds=m.seeds(), delay_override=0.01)
        sp.run(max_pages=5)
        n1 = len(m.hits("a"))
        sp2 = Spider(home, allow=mock_allowlist(), seeds=m.seeds(), delay_override=0.01)
        assert sp2.seen == sp.seen and len(sp2.frontier) == len(sp.frontier)
        sp2.run(max_pages=100)
        hits = m.hits("a")
        assert len(set(hits[n1:]) & {"/docs/1.html"}) == 0 or hits.count("/docs/1.html") == 1


def test_images_keep_alt_text(home):
    with MockWeb() as m:
        sp, _ = run_spider(home, m)
    rows = [json.loads(l) for l in (sp.out / "pages.jsonl").read_text().splitlines()]
    imgs = [r for r in rows if r["kind"] == "image_file"]
    assert imgs and all(r["alt"] for r in imgs)
    assert not any("999999" in r["url"] for r in imgs), "image without alt text should not be fetched"


def test_extract_and_license():
    ex = extract('<html><head><title>T</title><link rel="license" href="https://creativecommons.org/licenses/by/4.0/"></head>'
                 '<body><pre><code>x = 1</code></pre><img src="a.png" alt="a red star"><a href="/b">b</a></body></html>', "http://h/x")
    assert ex["license"] == "CC-BY" and ex["code"] == ["x = 1"] and ex["images"][0]["alt"] == "a red star"
    assert ex["links"] == ["http://h/b"]
    assert detect_license("Copyright (c) 2020. All rights reserved. Redistribution ... BSD-3-Clause") == "BSD-3-Clause"
    assert detect_license("Copyright 2024 Corp. All rights reserved.") == "ALL-RIGHTS-RESERVED"
    assert extract('<meta name="robots" content="noai">hi', "http://h/")["no_train"]


def test_robots_fetched_once_without_delay_override(home):
    """Regression: robots.txt fetch must not recurse through crawl-delay lookup (caused repeated robots requests)."""
    home["crawler"]["default_delay_s"] = 0.01
    with MockWeb() as m:
        sp = Spider(home, allow=mock_allowlist(), seeds=[{"url": m.url("a", "/docs/1.html"), "category": "code"}])
        sp.run(max_pages=4)
        assert m.hits("a").count("/robots.txt") == 1
        assert sp.robots.crawl_delay(m.url("a", "/")) == 0.05
