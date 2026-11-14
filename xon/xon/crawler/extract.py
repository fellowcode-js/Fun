"""HTML extraction: text, links, code blocks, images (+alt/caption), license and no-train signals."""
from __future__ import annotations

import html as htmllib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag

LICENSE_PATTERNS = [
    (r"\bMIT License\b|\bLicensed under the MIT\b|SPDX-License-Identifier:\s*MIT\b", "MIT"),
    (r"Apache License,? Version 2\.0|SPDX-License-Identifier:\s*Apache-2\.0", "Apache-2.0"),
    (r"\bBSD[- ]3[- ]Clause\b|SPDX-License-Identifier:\s*BSD-3-Clause", "BSD-3-Clause"),
    (r"\bBSD[- ]2[- ]Clause\b|SPDX-License-Identifier:\s*BSD-2-Clause", "BSD-2-Clause"),
    (r"Python Software Foundation License|\bPSF[- ]2\.0\b|PSF License", "PSF-2.0"),
    (r"\bCC0\b|creativecommons\.org/publicdomain/zero", "CC0-1.0"),
    (r"creativecommons\.org/licenses/by-sa/|\bCC BY-SA\b", "CC-BY-SA"),
    (r"creativecommons\.org/licenses/by/|\bCC BY\b(?!-)", "CC-BY"),
    (r"\bISC License\b|SPDX-License-Identifier:\s*ISC", "ISC"),
    (r"\bUnlicense\b|unlicense\.org", "Unlicense"),
    (r"All rights reserved", "ALL-RIGHTS-RESERVED"),
]
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "PSF-2.0", "CC0-1.0", "CC-BY", "ISC",
              "Unlicense", "0BSD", "CC-BY-SA", "W3C-doc"}
BLOCKED_LICENSES = {"ALL-RIGHTS-RESERVED", "NO-TRAIN"}


def detect_license(text: str, meta_license: str | None = None) -> str | None:
    if meta_license:
        for pat, name in LICENSE_PATTERNS:
            if re.search(pat, meta_license, re.I):
                return name
    found = None
    for pat, name in LICENSE_PATTERNS:
        if re.search(pat, text[:20000], re.I) or re.search(pat, text[-5000:], re.I):
            found = name
            if name != "ALL-RIGHTS-RESERVED":
                return name  # e.g. BSD text also says "All rights reserved": the license wins
    return found


class _Parser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section", "article", "pre", "table", "header", "footer"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.text: list[str] = []
        self.links: list[str] = []
        self.images: list[dict] = []
        self.code: list[str] = []
        self.styles: list[str] = []
        self.svgs: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.forms = 0
        self._skip = 0
        self._in_pre = 0
        self._pre_buf: list[str] = []
        self._in_style = False
        self._in_title = False
        self._svg_depth = 0
        self._svg_buf: list[str] = []
        self._fig_caption: list[str] | None = None
        self._last_img: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._svg_depth:
            self._svg_depth += 1
            self._svg_buf.append(self.get_starttag_text() or "")
            return
        if tag == "svg":
            self._svg_depth = 1
            self._svg_buf = [self.get_starttag_text() or ""]
            return
        if tag in self.SKIP:
            self._skip += 1
            if tag == "style":
                self._in_style = True
            return
        if tag == "title":
            self._in_title = True
        if tag == "a" and a.get("href"):
            self.links.append(urldefrag(urljoin(self.base, a["href"]))[0])
        elif tag == "link" and a.get("rel") and "license" in a.get("rel", ""):
            self.meta["license"] = a.get("href", "")
        elif tag == "link" and a.get("rel") == "stylesheet" and a.get("href"):
            self.links.append(urljoin(self.base, a["href"]))
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in ("robots", "license", "dc.rights", "copyright", "description"):
                self.meta[name] = a.get("content", "")
        elif tag == "img" and a.get("src"):
            self._last_img = {"src": urljoin(self.base, a["src"]), "alt": (a.get("alt") or "").strip(),
                              "title": a.get("title", ""), "caption": ""}
            self.images.append(self._last_img)
        elif tag == "figcaption":
            self._fig_caption = []
        elif tag == "form":
            self.forms += 1
        elif tag == "pre":
            self._in_pre += 1
            self._pre_buf = []
        if tag in self.BLOCK:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if self._svg_depth:
            self._svg_buf.append(f"</{tag}>")
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self.svgs.append("".join(self._svg_buf))
            return
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
            self._in_style = False
            return
        if tag == "title":
            self._in_title = False
        elif tag == "figcaption" and self._fig_caption is not None:
            cap = " ".join("".join(self._fig_caption).split())
            if self.images:
                self.images[-1]["caption"] = cap
            self._fig_caption = None
        elif tag == "pre" and self._in_pre:
            self._in_pre -= 1
            block = "".join(self._pre_buf).strip("\n")
            if block.strip():
                self.code.append(block)

    def handle_data(self, data):
        if self._svg_depth:
            self._svg_buf.append(htmllib.escape(data))
            return
        if self._in_style:
            self.styles.append(data)
            return
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._fig_caption is not None:
            self._fig_caption.append(data)
        if self._in_pre:
            self._pre_buf.append(data)
        self.text.append(data)


def extract(html: str, url: str) -> dict:
    p = _Parser(url)
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    text = re.sub(r"[ \t]+", " ", "".join(p.text))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    robots_meta = p.meta.get("robots", "").lower()
    no_train = any(k in robots_meta for k in ("noai", "noimageai", "notrain")) or bool(
        re.search(r"\b(no ai training|do not train|not for ai training)\b", text, re.I))
    lic = detect_license(text + " " + " ".join(p.meta.values()), p.meta.get("license"))
    if no_train:
        lic = "NO-TRAIN"
    # nearby text for images without captions
    for im in p.images:
        if not im["caption"] and im["alt"]:
            im["caption"] = im["alt"]
    return {
        "url": url, "title": " ".join(p.title.split()), "text": text, "links": list(dict.fromkeys(p.links)),
        "images": p.images, "code": p.code, "css": "\n".join(p.styles), "svgs": p.svgs[:20], "meta": p.meta,
        "license": lic, "no_train": no_train, "noindex": "noindex" in robots_meta, "forms": p.forms,
    }
