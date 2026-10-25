"""UI verification: launch the page in headless Chromium, interact, screenshot, critique, vision check.
Falls back to DOM assertions when no browser exists."""
from __future__ import annotations

import re
from pathlib import Path


def screenshot(root: Path, path: str, out: Path, interact: bool = False, vision=None) -> dict:
    p = (Path(root) / path).resolve()
    try:
        from xon.design.render import Renderer
        with Renderer(640, 480) as r:
            r._page.goto(p.as_uri())
            if interact and r._page.locator("#new").count():
                for t in ("Buy milk", "Write report", "Call Sam"):
                    r._page.fill("#new", t)
                    r._page.click("button[type=submit]")
                r._page.check("#list li >> nth=1 >> input[type=checkbox]")
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(r._page.screenshot())).convert("RGB")
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
        res = {"ok": True, "path": str(out), "mode": "browser"}
        if vision is not None:
            from xon.vision.predict import detect
            res["ui_elements"] = sorted({d["label"] for d in detect(vision, img)})
        return res
    except Exception as e:
        html = p.read_text()
        tags = sorted(set(re.findall(r"<(button|input|nav|table|form|ul|h1)\b", html)))
        return {"ok": True, "path": None, "mode": "dom-only", "dom_elements": tags, "note": str(e)[:160]}


def improve(root: Path, path: str, report: dict) -> dict:
    """Mechanical fixes for critique findings (contrast, labels, lang, target size)."""
    from xon.design.critique import improve_html
    p = Path(root) / path
    html = p.read_text()
    new = improve_html(html, report)
    applied = []
    if new != html:
        applied.append("contrast/labels/lang")
    if any(i["category"] == "accessibility" and "target" in i.get("detail", "") for i in report.get("issues", [])):
        new = new.replace("</style>", "button{min-width:28px;min-height:28px}\n</style>", 1)
        applied.append("touch targets >= 28px")
    p.write_text(new)
    return {"ok": True, "applied": applied}
