"""Serve a project folder on localhost, open a page in headless Chromium, screenshot it, optionally run DOM checks."""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SPEC = {"name": "serve", "description": "Serve a folder locally and screenshot a page (DOM checks: list of CSS selectors that must exist).",
        "params": {"folder": "str?", "page": "str?", "out": "str?", "expect": "list?"}}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def run(ctx, folder: str = ".", page: str = "index.html", out: str = "", expect: list | None = None) -> dict:
    root = ctx.path(folder)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{page}"
    try:
        from xon.design.render import Renderer
        with Renderer(1024, 700) as r:
            errors = []
            r._page.on("pageerror", lambda e: errors.append(str(e)))
            resp = r._page.goto(url, wait_until="load")
            missing = [sel for sel in (expect or []) if r._page.locator(sel).count() == 0]
            shot = ctx.path(out or f".xon/shots/{page.replace('/', '_')}.png")
            shot.parent.mkdir(parents=True, exist_ok=True)
            r._page.screenshot(path=str(shot), full_page=True)
        return {"ok": resp is not None and resp.status < 400 and not missing and not errors, "url": url,
                "status": resp.status if resp else None, "js_errors": errors[:10], "missing": missing,
                "screenshot": str(shot.relative_to(ctx.root))}
    finally:
        srv.shutdown()
