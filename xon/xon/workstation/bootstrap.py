"""`xon init`: probe hardware/network/browser, pick a tier, size the run to the budget, write xon.toml."""
from __future__ import annotations

import json
import time
from pathlib import Path

from xon import config
from xon.workstation import budget, probe


def init(root: Path, budget_str: str | None = None, gpu_price: float = 0.0, tier: str | None = None,
         live: bool | None = None, bench_steps: int = 100, quiet: bool = False) -> dict:
    root = Path(root)
    cfg = config.load(root)
    p = probe.probe()
    t = tier or probe.pick_tier(p)
    if budget_str and str(budget_str).startswith("$"):
        hours = budget.hours_from_dollars(float(budget_str[1:]), gpu_price)
    else:
        hours = budget.parse_budget(budget_str, cfg["budget"]["wall_hours"])
    plan = budget.size_run(hours, t, vocab=4096, seq_len=256 if t == "A" else 1024, gpu_price=gpu_price,
                           bench_steps=bench_steps)
    cfg["xon"]["tier"] = t
    cfg["budget"].update({"wall_hours": hours, "gpu_price_per_hour": gpu_price})
    net_ok = p.get("network", {}).get("ok", False)
    cfg["crawler"]["live"] = net_ok if live is None else live
    # time split for one cycle (Tier A demo must finish < 30 min)
    lm_min = max(1.0, plan["train_seconds"] / 60)
    cfg["lm"]["minutes"] = round(min(lm_min, hours * 60 * 0.35), 2)
    cfg["vision"]["minutes"] = round(max(1.0, hours * 60 * 0.15), 2)
    cfg.setdefault("practice", {})["limit"] = 10 if t == "A" else 200
    cfg["plan"] = {"tokens": plan["tokens"], "params": plan["params"], "lm": plan["lm"]}
    gpu_hours = hours if p["gpu"].get("cuda") else 0.0
    cfg["governor"]["max_gpu_hours"] = round(gpu_hours * 1.1, 2)
    config.save(cfg, root)
    hw = {"probe": p, "tier": t, "plan": plan, "t": time.time()}
    d = config.path(cfg, "data")
    (d / "hardware.json").write_text(json.dumps(hw, indent=1, default=str))
    if not quiet:
        print(f"XON init: {p['cpu_count']} CPU, {p['ram_gb']} GB RAM, GPU: {p['gpu'].get('name') or 'none'}, "
              f"disk free {p['disk_free_gb']} GB, network {'ok' if net_ok else 'OFFLINE'}, "
              f"browser {'ok' if p['browser']['ok'] else 'missing'}")
        print(f"XON tier {t} selected.")
        print(budget.describe(plan))
        if not plan["fits"]:
            print(f"XON REFUSES to start: {plan['reason']}. Increase --budget.")
        print(f"wrote {root / 'xon.toml'}")
    return hw
