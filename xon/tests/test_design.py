import json
from pathlib import Path

import pytest
from conftest import needs_browser

from xon.design import brand, from_prompt, palette, similarity, tokens

ROOT = Path(__file__).resolve().parent.parent


def test_contrast_matches_wcag_reference_cases():
    for line in (ROOT / "evalsets" / "contrast_cases.jsonl").read_text().splitlines():
        c = json.loads(line)
        assert abs(palette.contrast(c["fg"], c["bg"]) - c["ratio"]) < 0.02, c


def test_generated_palette_passes_its_checks():
    for base in ("#2f5fd0", "#e0b000", "#00c853", "#ff4081"):
        for dark in (False, True):
            p = palette.generate(base, dark)
            assert all(v["pass"] for v in p["checks"].values()), (base, dark, p["checks"])


def test_type_scale_and_blend():
    s = palette.type_scale(16, 1.25)
    assert s["sizes"]["lg"] == 20 and s["sizes"]["sm"] == 12.8
    assert len(s["issues"]) == 1 and s["issues"][0].startswith("xs=10.24px")
    assert palette.blend("rgba(0, 0, 0, 0.5)", "#ffffff") == (127.5, 127.5, 127.5)


def test_brand_refusal():
    assert brand.check("make a clone of the Netflix login page with their logo")
    assert brand.check("a page that looks exactly like Airbnb branding")
    assert brand.check("a landing page for my bakery with three cards") is None
    with pytest.raises(from_prompt.Refused):
        from_prompt.generate("copy the Google logo")


def test_from_prompt_parses_sections():
    spec = from_prompt.parse("A dark dashboard called Orbit with four feature cards, a table and a contact form with name and email")
    kinds = [s["kind"] for s in spec["sections"]]
    assert kinds[0] == "nav" and "cards" in kinds and "table" in kinds and "form" in kinds
    assert spec["palette"]["dark"] and spec["sections"][0]["brand"] == "Orbit"
    cards = next(s for s in spec["sections"] if s["kind"] == "cards")
    assert len(cards["items"]) == 4


def test_similarity_bounds():
    from PIL import Image
    a = Image.new("RGB", (64, 48), "white")
    b = Image.new("RGB", (64, 48), "black")
    assert similarity.fidelity(a, a) > 0.99 and similarity.fidelity(a, b) < 0.5


@needs_browser
def test_critique_finds_seeded_defects():
    from xon.design.critique import critique_html
    bad = ('<html><body><h2 style="font-size:30px">Big</h2><h1 style="font-size:14px">small</h1>'
           '<button style="background:#ffeb3b;color:#fff;width:20px;height:18px">Go</button><img src="x.png"><input></body></html>')
    r = critique_html(bad)
    cats = {i["category"] for i in r["issues"]}
    assert {"contrast", "hierarchy", "accessibility"} <= cats
    c = next(i for i in r["issues"] if i["category"] == "contrast")
    assert c["ratio"] < 1.5  # white on yellow, computed
    good = from_prompt.generate("a landing page with three feature cards and a newsletter form with email")
    rg = critique_html(good["html"])
    assert rg["contrast_failed"] == 0 and rg["score"] >= 80


@needs_browser
def test_tokens_extracted_from_page():
    t = tokens.from_html('<html><body style="background:#fafafa;color:#222;font-family:Georgia">'
                         '<div style="padding:8px;margin:16px;border-radius:6px;background:#3366cc">x</div><p>hello world</p></body></html>')
    assert t["color"]["background"] == "#fafafa" and t["color"]["text"] == "#222222"
    assert 8 in t["space"] and 16 in t["space"] and 6 in t["radius"] and "Georgia" in t["font"]["family"]
    assert "--color-background: #fafafa;" in tokens.to_css(t)


@needs_browser
def test_synthetic_ui_render_has_dom_labels(tmp_path):
    from xon.datasets import synth_ui
    rows = synth_ui.generate(tmp_path, 3, start_seed=5)
    assert len(rows) == 3 and all((tmp_path / r["image"]).exists() for r in rows)
    labels = {b["label"] for r in rows for b in r["boxes"]}
    assert labels and labels <= set(synth_ui.UI_CLASSES)
    assert all(0 <= b["x"] < 640 and b["w"] > 0 for r in rows for b in r["boxes"])


def test_gui_prompts_parse_to_app_layouts():
    s = from_prompt.parse_gui("a settings screen called Notely with tabs, toggles for email alerts and dark mode, a language dropdown and a volume slider")
    assert s["kind"] == "settings" and s["toggles"] == ["Email alerts", "Dark mode"] and "Language" in s["selects"] and s["sliders"] == ["Volume"]
    w = from_prompt.parse_gui("a desktop app window called Pixel Studio with a sidebar with layers, brushes and history")
    assert w["kind"] == "window" and w["sidebar"] == ["Layers", "Brushes", "History"]
    assert from_prompt.parse_gui("a dashboard with a sidebar and a table")["sidebar"][0] == "Overview"
    assert from_prompt.parse_gui("a landing page for a bakery") is None


def test_snap_grid_only_touches_spacing():
    html = "<style>.a{padding:7px 10px;margin:3px;color:#111;width:13px}</style><p style='padding:7px'>x</p>"
    out = from_prompt.snap_grid(html)
    assert "padding:8px 8px" in out and "margin:4px" in out and "width:13px" in out and "style='padding:7px'" in out


@needs_browser
def test_v2_gui_renders_new_controls_and_scores_well(tmp_path):
    from xon.datasets import synth_ui
    from xon.design.critique import critique_html
    rows = synth_ui.generate(tmp_path, 8, start_seed=777, version=2)
    labels = {b["label"] for r in rows for b in r["boxes"]}
    assert {"toggle", "select", "sidebar"} & labels
    g = from_prompt.generate("a settings screen with tabs, toggles for email alerts, a theme dropdown and a volume slider")
    assert g["engine"] == "spec-gui" and critique_html(g["html"])["score"] >= 90


def test_codegen_harvests_task_examples():
    from xon.agent.tools.codegen import examples_from_task
    assert examples_from_task("slugify, e.g. 'Hello World!' -> 'hello-world'", "slugify") == ["assert slugify('Hello World!') == 'hello-world'"]
    assert examples_from_task("so add(2, 3) == 5", None) == ["assert add(2, 3) == 5"]
