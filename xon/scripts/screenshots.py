"""Capture milestone screenshots into screenshots/: dashboard, design outputs, training curves, agent at work.
Usage: python scripts/screenshots.py <milestone-prefix> [--agent-artifacts DIR]"""
import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from xon import config  # noqa: E402
from xon.design.render import Renderer  # noqa: E402

OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)


def dashboard(prefix, r, cfg):
    from xon.workstation.dashboard.server import serve
    srv = serve(cfg, port=0, background=True)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    page = r._page
    page.set_viewport_size({"width": 1400, "height": 900})
    page.goto(url)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / f"{prefix}-dashboard.png"), full_page=True)
    # training curves close-up
    el = page.locator("svg#lm")
    if el.count():
        page.locator(".card", has=page.locator("svg#lm")).screenshot(path=str(OUT / f"{prefix}-lm-loss.png"))
        page.locator(".card", has=page.locator("svg#vis")).screenshot(path=str(OUT / f"{prefix}-vision-loss.png"))
    srv.shutdown()


def terminal(prefix, name, title, lines, r):
    body = "".join(f"<div class='{c}'>{html.escape(t)}</div>" for c, t in lines)
    doc = f"""<html><head><style>body{{margin:0;background:#0d1117;color:#c9d1d9;font:13px/1.5 'DejaVu Sans Mono',monospace}}
.bar{{background:#161b22;padding:8px 14px;color:#8b949e;border-bottom:1px solid #30363d}}.wrap{{padding:12px 16px}}
.cmd{{color:#7ee787}}.ok{{color:#56d364}}.err{{color:#ff7b72}}.dim{{color:#8b949e}}.hd{{color:#d2a8ff;font-weight:bold}}
.n{{color:#c9d1d9}}</style></head><body><div class='bar'>{html.escape(title)}</div><div class='wrap'>{body}</div></body></html>"""
    page = r._page
    page.set_viewport_size({"width": 1100, "height": 700})
    page.set_content(doc)
    page.screenshot(path=str(OUT / f"{prefix}-{name}.png"), full_page=True)


def agent_log(prefix, art_dir: Path, r, name="agent"):
    art_dir = Path(art_dir)
    plan = (art_dir / "plan.md").read_text().splitlines() if (art_dir / "plan.md").exists() else []
    log = [json.loads(l) for l in (art_dir / "log.jsonl").read_text().splitlines()] if (art_dir / "log.jsonl").exists() else []
    summ = json.loads((art_dir / "summary.json").read_text()) if (art_dir / "summary.json").exists() else {}
    lines = [("cmd", f"$ xon agent \"{summ.get('task', '')}\" --mode full-auto")]
    lines += [("hd" if l.startswith("#") else "dim", l) for l in plan if l.strip()]
    for e in log:
        args = e.get("args", {})
        a = args.get("path") or args.get("action") or args.get("target") or args.get("cmd") or args.get("tests") or ""
        lines.append(("ok" if e.get("ok") else "err", f"[{e['tool']:>11}] {a}  {'ok' if e.get('ok') else 'FAILED: ' + str(e.get('error'))[:80]}  ({e['ms']} ms)"))
    lines.append(("hd", "summary"))
    for k, v in summ.items():
        if k in ("diff", "task"):
            continue
        lines.append(("n", f"  {k}: {str(v)[:150]}"))
    terminal(prefix, name, f"XON agent - {art_dir.name}", lines, r)


def side_by_side(prefix, name, a: Path, b: Path, labels=("before", "after")):
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    from PIL import ImageDraw
    W = ia.width + ib.width + 30
    g = Image.new("RGB", (W, max(ia.height, ib.height) + 34), "white")
    g.paste(ia, (10, 30))
    g.paste(ib, (ia.width + 20, 30))
    d = ImageDraw.Draw(g)
    d.text((12, 8), labels[0], fill=(30, 30, 30))
    d.text((ia.width + 22, 8), labels[1], fill=(30, 30, 30))
    g.save(OUT / f"{prefix}-{name}.png")


if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%H%M")
    cfg = config.load(ROOT)
    with Renderer(1400, 900) as r:
        dashboard(prefix, r, cfg)
        for i, a in enumerate(sys.argv[2:]):
            agent_log(prefix, Path(a), r, name=f"agent{i or ''}")
    print("saved to", OUT)
