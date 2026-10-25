"""Headless-browser rendering: HTML -> screenshot + DOM element boxes + computed styles.

Falls back to a DOM-only mode (no pixels) when no browser is available.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from xon.workstation.probe import find_chromium

# JS run in the page: every element tagged data-xon="<label>" gets its box; plus style tokens.
_BOXES_JS = """
() => {
  const out = [];
  for (const el of document.querySelectorAll('[data-xon]')) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    out.push({label: el.dataset.xon, x: r.x, y: r.y, w: r.width, h: r.height});
  }
  return out;
}
"""

_STYLES_JS = """
() => {
  const els = [...document.body.querySelectorAll('*')].slice(0, 1500);
  const out = [];
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const cs = getComputedStyle(el);
    const ownText = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    out.push({tag: el.tagName.toLowerCase(), cls: el.className && el.className.baseVal === undefined ? el.className : '',
      x: r.x, y: r.y, w: r.width, h: r.height, text: ownText.slice(0, 80),
      color: cs.color, bg: cs.backgroundColor, font: cs.fontFamily, size: parseFloat(cs.fontSize),
      weight: cs.fontWeight, pad: [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].map(parseFloat),
      margin: [cs.marginTop, cs.marginRight, cs.marginBottom, cs.marginLeft].map(parseFloat),
      radius: parseFloat(cs.borderTopLeftRadius) || 0, alt: el.getAttribute('alt'),
      aria: el.getAttribute('aria-label'), role: el.getAttribute('role'),
      focusable: el.tabIndex >= 0, type: el.getAttribute('type'),
      labelled: !!(el.id && document.querySelector(`label[for="${el.id}"]`)) || !!el.closest('label') || !!el.getAttribute('aria-label') || !!el.getAttribute('placeholder')});
  }
  return out;
}
"""


class Renderer:
    """Context manager around one Chromium instance; reuse it for many renders."""

    def __init__(self, width: int = 640, height: int = 480):
        self.width, self.height = width, height
        self.executable = find_chromium()
        self._pw = self._browser = self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {"args": ["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"]}
        try:
            self._browser = self._pw.chromium.launch(**kw)
            self.executable = "playwright-default"
        except Exception:
            if not self.executable:
                self._pw.stop()
                raise RuntimeError("no headless Chromium found; run `playwright install chromium` or set XON_CHROMIUM")
            self._browser = self._pw.chromium.launch(executable_path=self.executable, **kw)
        self._page = self._browser.new_page(viewport={"width": self.width, "height": self.height})
        return self

    def __exit__(self, *a):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()

    def _load(self, html: str, width: int | None, height: int | None):
        w, h = width or self.width, height or self.height
        if self._page.viewport_size != {"width": w, "height": h}:
            self._page.set_viewport_size({"width": w, "height": h})
        self._page.set_content(html, wait_until="load")

    def screenshot_html(self, html: str, width: int | None = None, height: int | None = None,
                        full_page: bool = False) -> Image.Image:
        self._load(html, width, height)
        png = self._page.screenshot(full_page=full_page)
        return Image.open(io.BytesIO(png)).convert("RGB")

    def render(self, html: str, width: int | None = None, height: int | None = None, styles: bool = False) -> dict:
        self._load(html, width, height)
        png = self._page.screenshot()
        out = {"image": Image.open(io.BytesIO(png)).convert("RGB"), "boxes": self._page.evaluate(_BOXES_JS)}
        if styles:
            out["styles"] = self._page.evaluate(_STYLES_JS)
        return out

    def render_url(self, url: str, width: int | None = None, height: int | None = None, styles: bool = True) -> dict:
        w, h = width or self.width, height or self.height
        self._page.set_viewport_size({"width": w, "height": h})
        self._page.goto(url, wait_until="load", timeout=20000)
        png = self._page.screenshot()
        out = {"image": Image.open(io.BytesIO(png)).convert("RGB"), "boxes": self._page.evaluate(_BOXES_JS)}
        if styles:
            out["styles"] = self._page.evaluate(_STYLES_JS)
        return out


def available() -> bool:
    try:
        with Renderer() as r:
            r.screenshot_html("<p>x</p>", 32, 32)
        return True
    except Exception:
        return False


def save(img: Image.Image, p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p)
    return p
