"""Budget-driven sizing: pick params N and tokens D (~20 tokens/param) from measured throughput."""
from __future__ import annotations

import math
import time

import torch

from xon.lm.model import LMConfig, XONLM, shape_for_params

TOKENS_PER_PARAM = 20.0
TIER_BOUNDS = {  # (min, max) params; never hardcode a single size
    "A": (2.0e5, 1.2e7),
    "B": (5.0e7, 3.5e8),
    "C": (3.5e8, 3.0e9),
}


def parse_budget(s: str | float | None, default_hours: float = 0.5) -> float:
    """'8h', '30m', '2d', '1.5' (hours) -> hours."""
    if s is None or s == "":
        return default_hours
    if isinstance(s, (int, float)):
        return float(s)
    s = s.strip().lower()
    mult = {"m": 1 / 60, "h": 1.0, "d": 24.0}
    if s[-1] in mult:
        return float(s[:-1]) * mult[s[-1]]
    if s.startswith("$"):
        raise ValueError("dollar budgets need --gpu-price; use hours_from_dollars")
    return float(s)


def hours_from_dollars(dollars: float, price_per_hour: float) -> float:
    if price_per_hour <= 0:
        raise ValueError("gpu price per hour must be > 0 for a dollar budget")
    return dollars / price_per_hour


def device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def benchmark(cfg: LMConfig, steps: int = 100, batch: int = 8, dev: str | None = None,
              max_seconds: float = 60.0) -> dict:
    """Run up to `steps` real training steps on random tokens; return measured tokens/s and FLOP/s."""
    dev = dev or device()
    torch.manual_seed(0)
    m = XONLM(cfg).to(dev)
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
    x = torch.randint(0, cfg.vocab_size, (batch, cfg.seq_len + 1), device=dev)
    done, t0 = 0, None
    for i in range(steps):
        if i == 3:
            if dev == "cuda":
                torch.cuda.synchronize()
            t0 = time.time()
        _, loss = m(x[:, :-1], x[:, 1:])
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        if t0 is not None:
            done += 1
            if time.time() - t0 > max_seconds:
                break
    if dev == "cuda":
        torch.cuda.synchronize()
    dt = max(time.time() - (t0 or time.time()), 1e-6)
    tps = done * batch * cfg.seq_len / dt
    n = cfg.n_params()
    return {"steps": done, "tokens_per_s": tps, "flops_per_s": 6 * n * tps, "params": n, "device": dev}


def size_run(hours: float, tier: str, vocab: int = 4096, seq_len: int = 256, train_fraction: float = 0.35,
             bench: dict | None = None, gpu_price: float = 0.0, bench_steps: int = 100) -> dict:
    """Choose N and D jointly: D = 20 N and 6 N D <= FLOPs/s * T_train.

    train_fraction: share of the wall budget given to LM training (rest: crawl, vision, eval).
    """
    lo, hi = TIER_BOUNDS[tier]
    if bench is None:
        probe_cfg = shape_for_params(int(math.sqrt(lo * hi) if tier != "A" else 1.5e6), vocab, seq_len)
        bench = benchmark(probe_cfg, steps=bench_steps, max_seconds=30)
    flops = bench["flops_per_s"]
    t_train = hours * 3600 * train_fraction
    n_opt = math.sqrt(flops * t_train / (6 * TOKENS_PER_PARAM))
    n = min(max(n_opt, lo), hi)
    cfg = shape_for_params(int(n), vocab, seq_len)
    n_real = cfg.n_params()
    tokens = TOKENS_PER_PARAM * n_real
    est_tps = flops / (6 * n_real)
    est_s = tokens / est_tps
    if est_s > t_train:  # clamped at tier minimum: cut tokens to fit, and flag it
        tokens = est_tps * t_train
        est_s = t_train
    ckpt_mb = n_real * 4 * 3 / 1e6  # weights + adam moments
    data_gb = tokens * 2 / 1e9 * 2  # uint16 tokens, x2 for raw text
    fits = n_real >= lo * 0.5 and tokens >= 2 * n_real
    return {
        "tier": tier, "hours": hours, "train_seconds": round(est_s, 1),
        "params": n_real, "tokens": int(tokens), "tokens_per_param": round(tokens / n_real, 1),
        "lm": cfg.to_dict(), "bench": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in bench.items()},
        "est_disk_gb": round(ckpt_mb / 1e3 * 3 + data_gb, 3),
        "est_cost_usd": round(hours * gpu_price, 2),
        "fits": fits,
        "reason": "" if fits else "budget too small even for the tier's minimum model (needs >= 2 tokens/param)",
    }


def describe(plan: dict) -> str:
    return (f"XON plan: tier {plan['tier']}, budget {plan['hours']:.2f} h -> LM {plan['params']/1e6:.2f}M params, "
            f"{plan['tokens']/1e6:.1f}M tokens ({plan['tokens_per_param']} tok/param), "
            f"est. LM train {plan['train_seconds']/60:.1f} min at {plan['bench']['tokens_per_s']:.0f} tok/s "
            f"on {plan['bench']['device']}, disk ~{plan['est_disk_gb']} GB, cost ${plan['est_cost_usd']}")
