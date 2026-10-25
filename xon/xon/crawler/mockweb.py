"""Mock web for offline crawler tests and demos: a polite site, a 429 site and a 403 site."""
from __future__ import annotations

import io
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xon.datasets.shapes import SHAPES, make

FUNCS = [
    ("add", "a, b", "return a + b", "Return the sum of a and b."),
    ("clamp", "x, lo, hi", "return max(lo, min(hi, x))", "Clamp x into [lo, hi]."),
    ("is_even", "n", "return n % 2 == 0", "True if n is even."),
    ("reverse_words", "s", "return ' '.join(reversed(s.split()))", "Reverse word order."),
    ("count_vowels", "s", "return sum(1 for c in s.lower() if c in 'aeiou')", "Count vowels in s."),
    ("flatten", "xs", "return [y for x in xs for y in x]", "Flatten one level of nesting."),
    ("fib", "n", "a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a", "n-th Fibonacci number."),
    ("dedupe", "xs", "seen = set()\n    out = []\n    for x in xs:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out", "Remove duplicates keeping order."),
]


def _page(title: str, body: str, license_meta: str = "https://creativecommons.org/licenses/by/4.0/", extra_head: str = "") -> bytes:
    return (f'<!DOCTYPE html><html><head><title>{title}</title>{f'<link rel="license" href="{license_meta}">' if license_meta else ''}{extra_head}'
            f'<style>body{{font-family:sans-serif;color:#222;background:#fff}} .btn{{background:#3366cc;color:#fff;padding:8px 14px;border-radius:6px}}</style>'
            f"</head><body><h1>{title}</h1>{body}{'<footer>Content licensed CC BY 4.0</footer>' if license_meta else ''}</body></html>").encode()


def _site_a(path: str, base: str) -> tuple[int, str, bytes, dict]:
    if path == "/robots.txt":
        return 200, "text/plain", b"User-agent: *\nDisallow: /private/\nCrawl-delay: 0.05\n", {}
    if path in ("/", "/index.html"):
        links = ["/docs/1.html", "/docs/2.html", "/docs/3.html", "/code/funcs.py", "/code/more.py", "/design/tokens.html",
                 "/design/buttons.html", "/gallery/1.html", "/gallery/2.html", "/private/secret.html", "/login",
                 "/pii.html", "/adult.html", "/notrain.html", "/docs/1-copy.html", "/style.css", "/arr.html"]
        body = "<ul>" + "".join(f'<li><a href="{l}">{l}</a></li>' for l in links) + "</ul><p>Visit our <a href='https://unlisted.example.com/'>partner</a>.</p>"
        return 200, "text/html", _page("XON mock web", body), {}
    if path.startswith("/docs/"):
        n = path.split("/")[-1].split(".")[0].replace("-copy", "")
        i = int(n) % len(FUNCS)
        name, args, body, doc = FUNCS[i]
        txt = (f"<p>This tutorial explains how to write the function <code>{name}</code> in Python. {doc} "
               f"Functions are defined with the def keyword and return values with return. Tests are written with assert.</p>"
               f"<pre><code>def {name}({args}):\n    \"\"\"{doc}\"\"\"\n    {body}\n</code></pre>"
               f"<p>Next see <a href='/docs/{int(n) % 3 + 1}.html'>another page</a>.</p>")
        return 200, "text/html", _page(f"Tutorial {n}: {name}", txt), {}
    if path.startswith("/code/"):
        src = "# SPDX-License-Identifier: MIT\n# Copyright (c) XON mock authors. MIT License.\n\n"
        sel = FUNCS if "funcs" in path else FUNCS[::-1]
        for name, args, body, doc in sel:
            src += f'def {name}({args}):\n    """{doc}"""\n    {body}\n\n\n'
        src += 'if __name__ == "__main__":\n    assert add(2, 3) == 5\n'
        return 200, "text/x-python", src.encode(), {}
    if path == "/style.css":
        return 200, "text/css", b"/* MIT License */\n:root{--primary:#3366cc;--text:#222;--space:8px}\n.card{padding:16px;border-radius:8px;box-shadow:0 1px 3px #0003}\n", {}
    if path.startswith("/design/"):
        body = ("<p>Our design system uses an 8px spacing scale, a primary color #3366cc and text color #222222. "
                "Buttons need a contrast ratio of at least 4.5:1 against their background (WCAG AA).</p>"
                '<a class="btn" href="#">Primary</a>'
                '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M12 2l3 7h7l-5.5 4.5 2 7.5-6.5-4.5-6.5 4.5 2-7.5L2 9h7z" fill="#3366cc"/></svg>'
                "<pre><code>.btn { background: #3366cc; color: #ffffff; padding: 8px 14px; border-radius: 6px; }</code></pre>")
        return 200, "text/html", _page("Design tokens and buttons", body), {}
    if path.startswith("/gallery/"):
        g = int(path.split("/")[-1].split(".")[0])
        figs = ""
        for k in range(10):
            seed = g * 100 + k
            _, shape, color, cap = make(seed)
            figs += f'<figure><img src="/img/{seed}.png" alt="{cap}"><figcaption>{cap}</figcaption></figure>'
        figs += '<img src="/img/999999.png">'  # no alt text: should be skipped
        return 200, "text/html", _page(f"Gallery {g}", figs), {}
    if path.startswith("/img/"):
        seed = int(path.split("/")[-1].split(".")[0])
        img, *_ = make(seed)
        b = io.BytesIO()
        img.save(b, format="PNG")
        return 200, "image/png", b.getvalue(), {}
    if path == "/pii.html":
        return 200, "text/html", _page("Contact", "<p>Write to jane.doe@example.com or call +1 (555) 123-4567. "
                                       "Our key is sk-ABCDEF1234567890abcdef1234567890. Office: 42 Elm Street, Springfield. "
                                       "Python lists are ordered, mutable sequences and support slicing, sorting and comprehension syntax.</p>"), {}
    if path == "/adult.html":
        return 200, "text/html", _page("Adult", "<p>explicit porn xxx nsfw content here for testing the content filter only.</p>"), {}
    if path == "/notrain.html":
        return 200, "text/html", _page("No AI", "<p>Some text.</p>", extra_head='<meta name="robots" content="noai, noimageai">'), {}
    if path == "/arr.html":
        return 200, "text/html", _page("Rights", "<p>Copyright 2024 Example Corp. All rights reserved.</p>", license_meta=""), {}
    return 404, "text/plain", b"not found", {}


class _Handler(BaseHTTPRequestHandler):
    mode = "a"

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if self.server.mode == "429":  # type: ignore[attr-defined]
            code, ctype, body, hdr = 429, "text/plain", b"slow down", {"Retry-After": "1"}
            if path == "/robots.txt":
                code, body, hdr = 200, b"User-agent: *\nAllow: /\n", {}
        elif self.server.mode == "403":  # type: ignore[attr-defined]
            code, ctype, body, hdr = 403, "text/plain", b"forbidden", {}
            if path == "/robots.txt":
                code, body = 404, b""
        else:
            code, ctype, body, hdr = _site_a(path, "")
        self.server.hits.append(path)  # type: ignore[attr-defined]
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in hdr.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


class MockWeb:
    """Starts three servers on free ports. Use as a context manager."""

    def __init__(self):
        self.servers = {}

    def __enter__(self):
        for mode in ("a", "429", "403"):
            s = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            s.mode, s.hits = mode, []  # type: ignore[attr-defined]
            threading.Thread(target=s.serve_forever, daemon=True).start()
            self.servers[mode] = s
        return self

    def url(self, mode: str = "a", path: str = "/") -> str:
        host = "127.0.0.1" if mode != "429" else "localhost"
        return f"http://{host}:{self.servers[mode].server_address[1]}{path}"

    def hits(self, mode: str = "a") -> list[str]:
        return self.servers[mode].hits

    def seeds(self) -> list[dict]:
        return [{"url": self.url("a", "/"), "category": "code", "priority": 0},
                {"url": self.url("429", "/page.html"), "category": "general", "priority": 0},
                {"url": self.url("429", "/page2.html"), "category": "general", "priority": 0},
                {"url": self.url("403", "/x.html"), "category": "general", "priority": 0},
                {"url": self.url("403", "/y.html"), "category": "general", "priority": 0},
                {"url": self.url("403", "/z.html"), "category": "general", "priority": 0}]

    def __exit__(self, *a):
        for s in self.servers.values():
            s.shutdown()
            s.server_close()


def mock_allowlist() -> dict:
    import yaml
    from pathlib import Path
    al = yaml.safe_load((Path(__file__).parent / "allowlist.yaml").read_text())
    return al


if __name__ == "__main__":  # pragma: no cover
    import time
    with MockWeb() as m:
        print("XON mock web at", m.url("a"), m.url("429"), m.url("403"))
        while True:
            time.sleep(3600)
