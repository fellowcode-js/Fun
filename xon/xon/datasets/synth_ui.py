"""Synthetic UI generator: random layout spec -> HTML/CSS -> screenshot + DOM labels.

License-clean and unlimited. Each sample yields:
  spec (JSON layout), html (source), description (natural language), image (PNG), boxes (DOM labels).
Labels come for free from `data-xon` attributes, so UI detection needs no human labeling.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import random
from pathlib import Path

UI_CLASSES_V1 = ["button", "input", "nav", "card", "modal", "table", "icon"]
UI_CLASSES = UI_CLASSES_V1 + ["checkbox", "select", "tabs", "toggle", "slider", "sidebar"]
W, H = 640, 480

WORDS = ("cloud data team build ship plan sync fast secure simple smart open studio flow grid pixel note task "
         "board chart sales store photo music travel garden code learn shop health money home bike coffee").split()
FONTS = ["system-ui, sans-serif", "Georgia, serif", "'Courier New', monospace", "Verdana, sans-serif",
         "'Trebuchet MS', sans-serif"]
ICON_PATHS = {
    "star": "M12 2l3 7h7l-5.5 4.5 2 7.5-6.5-4.5-6.5 4.5 2-7.5L2 9h7z",
    "heart": "M12 21s-8-5.5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.5-8 11-8 11z",
    "home": "M3 11l9-8 9 8v10h-6v-6H9v6H3z",
    "search": "M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm9 17l-5-5",
    "bell": "M12 3a6 6 0 0 0-6 6v5l-2 3h16l-2-3V9a6 6 0 0 0-6-6zm-2 17h4",
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-8 9a8 8 0 0 1 16 0z",
}


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in rgb)


def random_palette(rng: random.Random) -> dict:
    h = rng.random()
    dark = rng.random() < 0.3
    s = rng.uniform(0.45, 0.85)
    primary = _hex(colorsys.hls_to_rgb(h, rng.uniform(0.38, 0.5), s))
    accent = _hex(colorsys.hls_to_rgb((h + rng.choice([0.33, 0.5, 0.08])) % 1, 0.5, s))
    if dark:
        bg, surface, text, muted = "#111418", _hex(colorsys.hls_to_rgb(h, 0.16, 0.15)), "#f2f4f7", "#a8b0bb"
    else:
        bg = _hex(colorsys.hls_to_rgb(h, rng.uniform(0.95, 0.99), 0.3))
        surface, text, muted = "#ffffff", "#1b1f24", "#5b6470"
    return {"bg": bg, "surface": surface, "primary": primary, "accent": accent, "text": text, "muted": muted,
            "dark": dark}


def _title(rng, n=2):
    return " ".join(rng.choice(WORDS).capitalize() for _ in range(n))


def random_spec(rng: random.Random) -> dict:
    pal = random_palette(rng)
    spec = {"palette": pal, "font": rng.choice(FONTS), "radius": rng.choice([0, 4, 8, 12]),
            "space": rng.choice([8, 12, 16]), "sections": []}
    secs = spec["sections"]
    if rng.random() < 0.85:
        secs.append({"kind": "nav", "brand": _title(rng, 1), "links": [rng.choice(WORDS).capitalize() for _ in range(rng.randint(2, 4))],
                     "icon": rng.choice(list(ICON_PATHS)) if rng.random() < 0.6 else None})
    body = rng.sample(["hero", "cards", "form", "table"], k=rng.randint(1, 3))
    for kind in body:
        if kind == "hero":
            secs.append({"kind": "hero", "title": _title(rng, rng.randint(2, 4)), "subtitle": " ".join(rng.choice(WORDS) for _ in range(8)),
                         "buttons": [_title(rng, 1) for _ in range(rng.randint(1, 2))], "align": rng.choice(["left", "center"])})
        elif kind == "cards":
            secs.append({"kind": "cards", "cols": rng.randint(2, 4), "items": [
                {"title": _title(rng, 2), "text": " ".join(rng.choice(WORDS) for _ in range(6)),
                 "icon": rng.choice(list(ICON_PATHS)) if rng.random() < 0.5 else None,
                 "button": _title(rng, 1) if rng.random() < 0.5 else None} for _ in range(rng.randint(2, 4))]})
        elif kind == "form":
            secs.append({"kind": "form", "title": _title(rng, 2),
                         "fields": [rng.choice(["Name", "Email", "City", "Phone", "Company", "Search"]) for _ in range(rng.randint(1, 3))],
                         "button": rng.choice(["Submit", "Send", "Join", "Save"])})
        else:
            cols = rng.randint(2, 4)
            secs.append({"kind": "table", "head": [rng.choice(WORDS).capitalize() for _ in range(cols)],
                         "rows": [[str(rng.randint(1, 999)) if c else rng.choice(WORDS) for c in range(cols)] for _ in range(rng.randint(2, 4))]})
    if rng.random() < 0.2:
        secs.append({"kind": "modal", "title": _title(rng, 2), "text": " ".join(rng.choice(WORDS) for _ in range(8)),
                     "button": rng.choice(["OK", "Close", "Confirm"])})
    return spec


def _icon(name: str, color: str, size: int = 20) -> str:
    return (f'<svg data-xon="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" aria-hidden="true"><path d="{ICON_PATHS[name]}"/></svg>')


def spec_to_html(spec: dict) -> str:
    p, r, s = spec["palette"], spec["radius"], spec["space"]
    css = f"""
*{{box-sizing:border-box}}body{{margin:0;background:{p['bg']};color:{p['text']};font-family:{spec['font']};font-size:14px}}
nav{{display:flex;align-items:center;gap:{s}px;padding:{s}px {s*2}px;background:{p['surface']};border-bottom:1px solid {p['muted']}33}}
nav .brand{{font-weight:700;font-size:18px;margin-right:auto;display:flex;gap:6px;align-items:center}}
nav a{{color:{p['text']};text-decoration:none}}
section{{padding:{s}px {s*2}px}}
h1{{font-size:28px;margin:{s//2}px 0}}h2{{font-size:18px;margin:{s//2}px 0}}p{{margin:4px 0;color:{p['muted']}}}
.btn{{background:{p['primary']};color:#fff;border:0;border-radius:{r}px;padding:8px 16px;font:inherit;font-weight:600;margin-right:8px}}
.btn.alt{{background:transparent;color:{p['primary']};border:2px solid {p['primary']}}}
.cards{{display:grid;gap:{s}px}}
.card{{background:{p['surface']};border-radius:{r}px;padding:{s}px;box-shadow:0 1px 3px #0002}}
input{{display:block;width:100%;max-width:320px;padding:7px 10px;border:1px solid {p['muted']};border-radius:{r}px;margin:6px 0;font:inherit;background:{p['surface']};color:{p['text']}}}
table{{border-collapse:collapse;background:{p['surface']};min-width:60%}}td,th{{border:1px solid {p['muted']}55;padding:5px 10px;text-align:left}}
th{{background:{p['primary']}22}}
.overlay{{position:fixed;inset:0;background:#0007;display:flex;align-items:center;justify-content:center}}
.modal{{background:{p['surface']};border-radius:{r}px;padding:{s*2}px;width:300px;box-shadow:0 8px 30px #0006}}
"""
    out = []
    for sec in spec["sections"]:
        k = sec["kind"]
        if k == "nav":
            icon = _icon(sec["icon"], p["primary"]) if sec.get("icon") else ""
            links = "".join(f'<a href="#">{l}</a>' for l in sec["links"])
            out.append(f'<nav data-xon="nav"><span class="brand">{icon}{sec["brand"]}</span>{links}</nav>')
        elif k == "hero":
            btns = "".join(f'<button data-xon="button" class="btn{" alt" if i else ""}">{b}</button>' for i, b in enumerate(sec["buttons"]))
            out.append(f'<section style="text-align:{sec["align"]}"><h1>{sec["title"]}</h1><p>{sec["subtitle"]}</p><div style="margin-top:10px">{btns}</div></section>')
        elif k == "cards":
            items = []
            for it in sec["items"]:
                ic = _icon(it["icon"], p["accent"], 24) if it.get("icon") else ""
                bt = f'<button data-xon="button" class="btn" style="margin-top:8px">{it["button"]}</button>' if it.get("button") else ""
                items.append(f'<div data-xon="card" class="card">{ic}<h2>{it["title"]}</h2><p>{it["text"]}</p>{bt}</div>')
            out.append(f'<section><div class="cards" style="grid-template-columns:repeat({sec["cols"]},1fr)">{"".join(items)}</div></section>')
        elif k == "form":
            fields = "".join(f'<input data-xon="input" aria-label="{f}" placeholder="{f}">' for f in sec["fields"])
            out.append(f'<section><h2>{sec["title"]}</h2><form>{fields}<button data-xon="button" class="btn" type="button">{sec["button"]}</button></form></section>')
        elif k == "table":
            head = "".join(f"<th>{h}</th>" for h in sec["head"])
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in sec["rows"])
            out.append(f'<section><table data-xon="table"><tr>{head}</tr>{rows}</table></section>')
        elif k == "modal":
            out.append(f'<div class="overlay"><div data-xon="modal" class="modal" role="dialog" aria-label="{sec["title"]}"><h2>{sec["title"]}</h2>'
                       f'<p>{sec["text"]}</p><button data-xon="button" class="btn">{sec["button"]}</button></div></div>')
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>{spec["sections"][0].get("brand", "Page") if spec["sections"] else "Page"}</title>'
            f"<style>{css}</style></head><body>\n" + "\n".join(out) + "\n</body></html>")


def describe(spec: dict) -> str:
    p = spec["palette"]
    parts = [f"A {'dark' if p['dark'] else 'light'} page using primary color {p['primary']}, "
             f"{spec['font'].split(',')[0].strip(chr(39))} font, {spec['radius']}px corners."]
    for sec in spec["sections"]:
        k = sec["kind"]
        if k == "nav":
            parts.append(f"A top nav with brand '{sec['brand']}' and links {', '.join(sec['links'])}.")
        elif k == "hero":
            parts.append(f"A {sec['align']}-aligned hero titled '{sec['title']}' with {len(sec['buttons'])} button(s): {', '.join(sec['buttons'])}.")
        elif k == "cards":
            parts.append(f"{len(sec['items'])} cards in {sec['cols']} columns: " + "; ".join(i['title'] for i in sec['items']) + ".")
        elif k == "form":
            parts.append(f"A form '{sec['title']}' with fields {', '.join(sec['fields'])} and a '{sec['button']}' button.")
        elif k == "table":
            parts.append(f"A table with columns {', '.join(sec['head'])} and {len(sec['rows'])} rows.")
        elif k == "modal":
            parts.append(f"A modal dialog '{sec['title']}' with a '{sec['button']}' button.")
    return " ".join(parts)


def sample(seed: int, version: int = 1) -> dict:
    rng = random.Random(seed)
    if version >= 2:
        spec = random_spec_v2(rng)
        html = spec_to_html_v2(spec)
        return {"id": f"synth2-{seed}", "seed": seed, "version": 2, "spec": spec, "html": html,
                "description": describe_v2(spec), "license": "CC0-1.0 (XON synthetic)", "source": "xon://synth_ui/v2"}
    spec = random_spec(rng)
    html = spec_to_html(spec)
    return {"id": f"synth-{seed}", "seed": seed, "spec": spec, "html": html, "description": describe(spec),
            "license": "CC0-1.0 (XON synthetic)", "source": "xon://synth_ui"}


def generate(out_dir: Path, n: int, start_seed: int = 0, renderer=None, gov=None, version: int = 1) -> list[dict]:
    """Render n samples into out_dir/{id}.png + index.jsonl. Returns metadata rows (no image objects)."""
    from xon.design.render import Renderer
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    own = renderer is None
    r = renderer or Renderer(W, H).__enter__()
    rows = []
    try:
        with open(out_dir / "index.jsonl", "a") as idx:
            for seed in range(start_seed, start_seed + n):
                if gov is not None:
                    gov.tick()
                s = sample(seed, version)
                res = r.render(s["html"], W, H)
                img_path = out_dir / f"{s['id']}.png"
                res["image"].save(img_path, optimize=True)
                row = {k: v for k, v in s.items()}
                row["image"] = img_path.name
                row["boxes"] = [b for b in res["boxes"] if b["label"] in UI_CLASSES]
                row["sha1"] = hashlib.sha1(s["html"].encode()).hexdigest()
                idx.write(json.dumps(row) + "\n")
                rows.append(row)
    finally:
        if own:
            r.__exit__(None, None, None)
    return rows


def load_index(d: Path) -> list[dict]:
    p = Path(d) / "index.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]



# ---------------------------------------------------------------- v2: app layouts, settings, desktop GUI windows
NAV_ITEMS = ["Overview", "Projects", "Reports", "Messages", "Team", "Billing", "Settings", "Files", "Calendar"]
SETTINGS = ["Email alerts", "Dark mode", "Auto-save", "Two-factor login", "Weekly digest", "Sound effects", "Beta features"]
SELECTS = {"Language": ["English", "Deutsch", "Español"], "Theme": ["System", "Light", "Dark"],
           "Region": ["Europe", "Americas", "Asia"], "Units": ["Metric", "Imperial"]}


def random_spec_v2(rng: random.Random) -> dict:
    kind = rng.choices(["app", "settings", "window", "pricing", "page"], [0.3, 0.2, 0.25, 0.1, 0.15])[0]
    pal = random_palette(rng)
    spec = {"v": 2, "kind": kind, "palette": pal, "font": rng.choice(FONTS[:2] + FONTS[3:]), "radius": rng.choice([4, 6, 8, 12]),
            "space": rng.choice([8, 12, 16]), "title": _title(rng, rng.randint(1, 2))}
    if kind == "page":
        spec["inner"] = random_spec(rng)
        return spec
    spec["sidebar"] = [rng.choice(NAV_ITEMS) for _ in range(rng.randint(4, 6))] if kind in ("app", "settings") or rng.random() < 0.3 else None
    spec["tabs"] = rng.sample(["General", "Advanced", "Privacy", "Activity", "Details", "Sharing"], k=rng.randint(2, 4)) if rng.random() < 0.6 else None
    spec["toggles"] = rng.sample(SETTINGS, k=rng.randint(1, 3)) if kind in ("settings", "window") or rng.random() < 0.3 else []
    spec["checks"] = rng.sample(SETTINGS, k=rng.randint(1, 3)) if rng.random() < 0.6 else []
    spec["selects"] = rng.sample(list(SELECTS), k=rng.randint(1, 2)) if rng.random() < 0.6 else []
    spec["sliders"] = rng.sample(["Volume", "Brightness", "Zoom", "Quality"], k=rng.randint(1, 2)) if rng.random() < 0.5 else []
    spec["stats"] = [(_title(rng, 1), str(rng.randint(10, 9999))) for _ in range(rng.randint(2, 4))] if kind == "app" else []
    spec["table"] = rng.random() < 0.4
    spec["plans"] = [(n, f"${p}") for n, p in zip(["Starter", "Pro", "Team"], sorted(rng.sample(range(5, 99), 3)))] if kind == "pricing" else []
    spec["buttons"] = [_title(rng, 1) for _ in range(rng.randint(1, 2))]
    return spec


def _toggle(label: str, on: bool, p: dict) -> str:
    knob = "left:18px" if on else "left:2px"
    return (f'<label class="row"><span>{label}</span><span data-xon="toggle" role="switch" aria-checked="{str(on).lower()}" '
            f'aria-label="{label}" class="tg" style="background:{p["primary"] if on else p["muted"] + "88"}">'
            f'<span class="kn" style="{knob}"></span></span></label>')


def spec_to_html_v2(spec: dict) -> str:
    if spec["kind"] == "page":
        return spec_to_html(spec["inner"])
    p, r, s = spec["palette"], spec["radius"], spec["space"]
    rng = random.Random(hash(spec["title"]) & 0xFFFF)
    css = f"""*{{box-sizing:border-box}}body{{margin:0;background:{p['bg']};color:{p['text']};font-family:{spec['font']};font-size:14px}}
.shell{{display:flex;min-height:480px}}aside{{width:150px;background:{p['surface']};border-right:1px solid {p['muted']}33;padding:{s}px 0}}
aside a{{display:block;padding:8px {s}px;min-height:32px;color:{p['text']};text-decoration:none;border-left:4px solid transparent}}aside a.on{{border-left-color:{p['primary']};font-weight:700;background:{p['muted']}1a}}
main{{flex:1;padding:{s}px {s + 4}px}}h1{{font-size:20px;margin:0 0 {s}px}}
.tabs{{display:flex;gap:4px;border-bottom:1px solid {p['muted']}44;margin-bottom:{s}px}}.tabs span{{padding:8px 12px}}.tabs .on{{border-bottom:4px solid {p['primary']};font-weight:700}}
.panel{{background:{p['surface']};border-radius:{r}px;padding:{s}px;margin-bottom:{s}px;box-shadow:0 1px 3px #0002}}
.row{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0}}
.tg{{position:relative;display:inline-block;width:36px;height:20px;border-radius:10px}}.kn{{position:absolute;top:2px;width:16px;height:16px;border-radius:50%;background:#fff}}
select{{padding:4px 8px;min-height:32px;border:1px solid {p['muted']};border-radius:{r}px;background:{p['surface']};color:{p['text']};font:inherit}}
input[type=range]{{width:160px;height:24px;accent-color:{p['primary']}}}input[type=checkbox]{{width:24px;height:24px;accent-color:{p['primary']}}}
.btn{{background:{p['primary']};color:{p.get('on_primary', '#fff')};border:0;border-radius:{r}px;padding:8px 16px;font:inherit;font-weight:600;margin-right:8px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:{s}px;margin-bottom:{s}px}}.stat b{{display:block;font-size:20px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid {p['muted']}33;padding:4px 8px;text-align:left}}
.win{{margin:18px auto;width:600px;border-radius:{r}px;overflow:hidden;box-shadow:0 10px 30px #0004;background:{p['surface']}}}
.bar{{display:flex;align-items:center;gap:8px;padding:8px 12px;background:{p['muted']}22;border-bottom:1px solid {p['muted']}33;font-weight:600}}
.dot{{width:11px;height:11px;border-radius:50%;display:inline-block}}.tools{{display:flex;gap:8px;padding:4px 12px;border-bottom:1px solid {p['muted']}22}}
.status{{padding:4px 12px;font-size:12px;color:{p['muted']};border-top:1px solid {p['muted']}22}}
.plans{{display:grid;grid-template-columns:repeat(3,1fr);gap:{s}px}}.plan b{{font-size:24px;display:block;margin:8px 0}}"""
    body = []
    if spec.get("tabs"):
        body.append('<div data-xon="tabs" class="tabs" role="tablist">' + "".join(
            f'<span role="tab" class="{"on" if i == 0 else ""}">{t}</span>' for i, t in enumerate(spec["tabs"])) + "</div>")
    if spec.get("stats"):
        body.append('<div class="stats">' + "".join(f'<div data-xon="card" class="panel stat">{k}<b>{v}</b></div>' for k, v in spec["stats"]) + "</div>")
    if spec.get("plans"):
        body.append('<div class="plans">' + "".join(
            f'<div data-xon="card" class="panel plan">{n}<b>{pr}</b><button data-xon="button" class="btn">Choose</button></div>'
            for n, pr in spec["plans"]) + "</div>")
    controls = []
    for t in spec.get("toggles", []):
        controls.append(_toggle(t, rng.random() < 0.5, p))
    for i, c in enumerate(spec.get("checks", [])):
        controls.append(f'<label class="row" for="c{i}"><span>{c}</span><input data-xon="checkbox" type="checkbox" id="c{i}" {"checked" if rng.random() < 0.5 else ""}></label>')
    for i, name in enumerate(spec.get("selects", [])):
        opts = "".join(f"<option>{o}</option>" for o in SELECTS[name])
        controls.append(f'<label class="row" for="s{i}"><span>{name}</span><select data-xon="select" id="s{i}">{opts}</select></label>')
    for i, name in enumerate(spec.get("sliders", [])):
        controls.append(f'<label class="row" for="r{i}"><span>{name}</span><input data-xon="slider" type="range" id="r{i}" value="{rng.randint(10, 90)}"></label>')
    if controls:
        body.append('<div class="panel">' + "".join(controls) + "</div>")
    if spec.get("table"):
        rows = "".join(f"<tr><td>{rng.choice(WORDS)}</td><td>{rng.randint(1, 99)}</td><td>{rng.choice(['Active', 'Paused'])}</td></tr>" for _ in range(3))
        body.append(f'<div class="panel"><table data-xon="table"><tr><th>Name</th><th>Count</th><th>Status</th></tr>{rows}</table></div>')
    body.append("<div>" + "".join(f'<button data-xon="button" class="btn">{b}</button>' for b in spec["buttons"]) + "</div>")
    inner = f'<h1>{spec["title"]}</h1>' + "".join(body)
    side = ""
    if spec.get("sidebar"):
        side = '<aside data-xon="sidebar"><nav aria-label="sections">' + "".join(
            f'<a href="#" class="{"on" if i == 0 else ""}">{n}</a>' for i, n in enumerate(spec["sidebar"])) + "</nav></aside>"
    if spec["kind"] == "window":
        dots = "".join(f'<span class="dot" style="background:{c}"></span>' for c in ("#ff5f57", "#febc2e", "#28c840"))
        tools = "".join(f'<button data-xon="button" class="btn" style="padding:4px 12px;min-height:28px;font-size:12px">{t}</button>' for t in ("New", "Open", "Save"))
        content = f'<div class="shell" style="min-height:300px">{side}<main>{inner}</main></div>' if side else f"<main>{inner}</main>"
        page = (f'<div class="win" role="application" aria-label="{spec["title"]}"><div data-xon="nav" class="bar">{dots}<span style="margin-left:8px">{spec["title"]}</span></div>'
                f'<div class="tools">{tools}</div>{content}<div class="status">Ready</div></div>')
    else:
        page = f'<div class="shell">{side}<main>{inner}</main></div>'
    return (f'<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>{spec["title"]}</title><style>{css}</style></head>'
            f"<body>\n{page}\n</body></html>")


def describe_v2(spec: dict) -> str:
    if spec["kind"] == "page":
        return describe(spec["inner"])
    kind = {"app": "dashboard app", "settings": "settings screen", "window": "desktop app window", "pricing": "pricing page"}[spec["kind"]]
    parts = [f"A {'dark' if spec['palette']['dark'] else 'light'} {kind} titled '{spec['title']}' with primary color {spec['palette']['primary']}."]
    if spec.get("sidebar"):
        parts.append(f"Left sidebar: {', '.join(spec['sidebar'])}.")
    if spec.get("tabs"):
        parts.append(f"Tabs: {', '.join(spec['tabs'])}.")
    for key, word in (("toggles", "toggle switches"), ("checks", "checkboxes"), ("selects", "dropdowns"), ("sliders", "sliders")):
        if spec.get(key):
            parts.append(f"{word.capitalize()}: {', '.join(spec[key])}.")
    if spec.get("stats"):
        parts.append(f"{len(spec['stats'])} stat cards.")
    if spec.get("plans"):
        parts.append("Three pricing plans: " + ", ".join(f"{n} {p}" for n, p in spec["plans"]) + ".")
    if spec.get("table"):
        parts.append("A data table.")
    parts.append(f"Buttons: {', '.join(spec['buttons'])}.")
    return " ".join(parts)
