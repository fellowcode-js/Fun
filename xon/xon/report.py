"""Generate REPORT.md from measured data only: hardware, live vs mock, data stats, per-tier numbers, evals,
cycle history, gates, licenses, known limits. Hand-written prose lives between the AUTO markers' outside."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from xon import config

START, END = "<!-- AUTO:START -->", "<!-- AUTO:END -->"


def _j(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def _fmt(v, d=3):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


def build(cfg: dict) -> str:
    ck, ex, data = config.path(cfg, "checkpoints"), config.path(cfg, "exchange"), config.path(cfg, "data")
    hw = _j(data / "hardware.json", {})
    pr = hw.get("probe", {})
    hist = [json.loads(l) for l in (ck / "history.jsonl").read_text().splitlines()] if (ck / "history.jsonl").exists() else []
    gates = _j(ex / "gates.json", {})
    crawl = config.jsonl_read(ex / "crawl_stats.jsonl")
    man = _j(ex / "shards" / "manifest.json", {"shards": []})
    kinds, lic = Counter(), Counter()
    for s in man["shards"]:
        kinds.update(s["kinds"])
        lic.update(s["licenses"])
    L = []
    L.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `xon report` from logs, eval files and gate results._\n")
    L.append("### Hardware (probed)\n")
    g = pr.get("gpu", {})
    L.append(f"| CPU | RAM | GPU | disk free | network | headless browser | tier |\n|---|---|---|---|---|---|---|\n"
             f"| {pr.get('cpu_count')} | {pr.get('ram_gb')} GB | {g.get('name') or 'none'} | {pr.get('disk_free_gb')} GB | "
             f"{(pr.get('network') or {}).get('detail', '?')} | {'yes' if (pr.get('browser') or {}).get('ok') else 'no'} | {hw.get('tier')} |\n")
    plan = hw.get("plan", {})
    if plan:
        L.append(f"Budget plan: {plan.get('hours')} h -> {plan.get('params', 0) / 1e6:.2f}M params, {plan.get('tokens', 0) / 1e6:.1f}M tokens "
                 f"({plan.get('tokens_per_param')} tok/param), measured {(plan.get('bench') or {}).get('tokens_per_s')} tok/s.\n")
    # expectations table
    L.append("### Honest expectations table (measured)\n")
    L.append("| tier | LM params | LM tokens seen | code pass@1 | code pass@5 | held-out ppl | bug-fix (blind) | design fidelity | "
             "UI detection F1@0.5 | recognition top-1 | zero-shot | wall-clock / cycle |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for h in hist:
        m = h["metrics"]
        L.append(f"| {hw.get('tier', '?')} | {h['lm'].get('params', 0) / 1e6:.2f}M | {h['lm'].get('tokens_seen', 0) / 1e6:.1f}M | "
                 f"{_fmt(m.get('code_pass@1'))} | {_fmt(m.get('code_pass@5'))} | {_fmt(m.get('code_ppl'), 2)} | "
                 f"{_fmt(m.get('bugfix_blind_rate'))} | {_fmt(m.get('design_fidelity'))} | {_fmt(m.get('ui_f1'))} | "
                 f"{_fmt(m.get('recog_top1'))} | {_fmt(m.get('recog_zero_shot'))} | {_fmt(h.get('minutes'), 1)} min |")
    L.append("\nTiers B and C were **not trained** (no GPU available). Their configs exist and are sized by the same code.\n")
    pe = _j(ck / "pretrained_eval.json", None)
    if pe:
        L.append(f"### Warm-start coder: {pe['model']} ({pe['license']}), CPU inference, frozen XON eval sets\n")
        L.append("| eval | pass@1 | pass@5 | greedy solved | solved by any of 5 |\n|---|---|---|---|---|")
        for lang, key in (("Python (62 problems)", "python"), ("C++ (28 problems)", "cpp")):
            r = pe[key]
            L.append(f"| {lang} | {_fmt(r['pass@1'])} | {_fmt(r['pass@5'])} | {r['greedy_solved']}/{r['problems']} | {r['solved_any']}/{r['problems']} |")
        bb, cb = pe.get("bugfix_blind.jsonl_combined", {}), pe.get("cpp_bugfix_blind.jsonl_combined", {})
        L.append(f"\nBug repair, blind sets, mutation search then LLM rewrite (every candidate verified by tests): Python "
                 f"{bb.get('repair_fixed')}/{bb.get('cases')} (by stage {bb.get('fixed_by_stage')}), C++ {cb.get('repair_fixed')}/{cb.get('cases')}. "
                 f"LLM rewrite alone (4 samples): dev {_fmt(pe.get('bugfix_rewrite_rate@4'))}, blind {_fmt(pe.get('bugfix_blind_rewrite_rate@4'))}.\n")
        L.append("Caveat: these problems are short and XON-written; the pretrained model may have seen similar functions in its "
                 "pretraining data, which cannot be ruled out.\n")
    if hist:
        h = hist[-1]
        det = _j(ck / f"cycle-{h['cycle']:03d}" / "eval_detail.json", {})
        m = h["metrics"]
        L.append("### Latest cycle detail\n")
        L.append("| metric | value | baseline / chance | note |\n|---|---|---|---|")
        L.append(f"| code pass@1 / pass@5 ({det.get('pass_k', {}).get('problems')} problems, 5 samples) | {_fmt(m['code_pass@1'])} / {_fmt(m['code_pass@5'])} | 0 | XON-written hidden tests |")
        L.append(f"| held-out perplexity (stdlib + HTML) | {_fmt(m['code_ppl'], 2)} | BPE vocab 4096 | bits/char {_fmt(m.get('code_bpc'))} |")
        bf, bfb = det.get("bugfix", {}), det.get("bugfix_blind", {})
        L.append(f"| bug-fix, dev set ({bf.get('cases')}) | {_fmt(m['bugfix_rate'])} | LM-only {_fmt(m['bugfix_lm_only'])} | repair tool tuned on this set |")
        L.append(f"| bug-fix, **blind** set ({bfb.get('cases')}) | {_fmt(m['bugfix_blind_rate'])} | LM-only {_fmt(m['bugfix_blind_lm_only'])} | never used for tuning |")
        L.append(f"| screenshot->code fidelity ({det.get('fidelity', {}).get('images')} held-out) | {_fmt(m['design_fidelity'])} | bg-only {_fmt(m['design_fidelity_baseline'])}, first layout {_fmt(m['design_fidelity_initial'])} | SSIM+color+edge, 0..1 |")
        if "ui_f1_v2" in m:
            L.append(f"| UI detection F1, v2 GUIs (13 classes) | {_fmt(m['ui_f1_v2'])} | – | per class: {det.get('ui_v2', {}).get('per_class_f1')} |")
        if "cpp_pass@1" in m:
            L.append(f"| XON LM C++ pass@1 / pass@5 | {_fmt(m['cpp_pass@1'])} / {_fmt(m['cpp_pass@5'])} | 0 | from-scratch model |")
        L.append(f"| UI detection P / R / F1 @IoU0.5 | {_fmt(m['ui_precision'])} / {_fmt(m['ui_recall'])} / {_fmt(m['ui_f1'])} | – | per class: {det.get('ui', {}).get('per_class_f1')} |")
        L.append(f"| recognition top-1 / top-5 / zero-shot | {_fmt(m['recog_top1'])} / {_fmt(m['recog_top5'])} / {_fmt(m['recog_zero_shot'])} | 0.100 | 10 procedural classes, 500 held-out |")
        L.append(f"| contrast checker accuracy | {_fmt(m['contrast_accuracy'])} | – | {det.get('contrast', {}).get('cases')} WCAG reference pairs |")
        L.append(f"| critique: seeded-defect recall | {_fmt(m['critique_recall'])} | – | generated page score {m['critique_generated_score']} |")
        ex_c = det.get("pass_k", {}).get("example_completion", "")
        if ex_c:
            L.append("\nExample LM completion (first eval problem, greedy):\n\n```python\n" + ex_c[:400] + "\n```\n")
    L.append("### Cycle history\n")
    L.append("| cycle | promoted | reason | new records | web images | pseudo-labeled | LM steps | LM min | vision steps | events |\n|---|---|---|---|---|---|---|---|---|---|")
    for h in hist:
        ev = [e["event"] for e in h.get("lm_events", []) + h.get("vision_events", [])]
        L.append(f"| {h['cycle']} | {'yes' if h['promoted'] else 'no'} | {h['reason'][:90]} | {h['data']['new_records']} | "
                 f"{h['data']['web_images']} | {h['data']['pseudo_labeled']} | {h['lm'].get('step')} | {h['lm'].get('minutes')} | "
                 f"{h['vision'].get('step')} | {', '.join(ev) or '–'} |")
    L.append("\n### Data\n")
    live = [c for c in crawl if c.get("live")]
    mock = [c for c in crawl if not c.get("live")]
    L.append(f"- Crawl rounds: {len(live)} live, {len(mock)} mock. Live pages fetched: {sum((c.get('crawl') or {}).get('fetched', 0) for c in live)}; "
             f"mock pages fetched: {sum((c.get('crawl') or {}).get('fetched', 0) for c in mock)}.")
    L.append(f"- Stored records by kind: {dict(kinds)}")
    rej = Counter()
    for c in crawl:
        rej.update({k: v for k, v in (c.get("clean") or {}).items() if k.startswith(("reject", "quarantine", "pii"))})
    L.append(f"- Rejects / quarantine / PII scrubs: {dict(rej)}")
    L.append(f"- Records by license: {dict(lic)}\n")
    L.append("### Gates\n")
    L.append("| gate | pass | key numbers |\n|---|---|---|")
    for k in ("m0", "m1", "m2", "m3", "m4"):
        gr = gates.get(k)
        if not gr:
            L.append(f"| {k.upper()} | not run | – |")
            continue
        keys = {kk: vv for kk, vv in gr.items() if kk not in ("t", "logs", "output", "metrics", "events", "home") and not isinstance(vv, (dict, list))}
        L.append(f"| {k.upper()} | {'PASS' if gr.get('pass') else 'FAIL'} | {keys} |")
    return "\n".join(L) + "\n"


def write(cfg: dict) -> Path:
    root = Path(cfg["_root"])
    p = root / "REPORT.md"
    body = build(cfg)
    cur = p.read_text() if p.exists() else f"# XON report\n\n{START}\n{END}\n"
    if START not in cur:
        cur += f"\n{START}\n{END}\n"
    pre, rest = cur.split(START, 1)
    _, post = rest.split(END, 1)
    p.write_text(pre + START + "\n" + body + END + post)
    return p
