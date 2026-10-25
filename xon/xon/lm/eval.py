"""Code evals on FROZEN sets: pass@1/pass@5 (hidden tests), bug-fix rate, held-out perplexity."""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch

from xon.agent.sandbox import run_tests_on
from xon.lm import generate, repair


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimator (Chen et al. 2021)."""
    if n - c < k:
        return 1.0
    return 1.0 - float(np.prod(1.0 - k / np.arange(n - c + 1, n + 1)))


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def code_pass_k(model, tok, evalsets: Path, n_samples: int = 5, limit: int | None = None, temperature: float = 0.8,
                max_new: int = 128) -> dict:
    probs = load(Path(evalsets) / "code_problems.jsonl")[:limit]
    jobs = []
    for p in probs:
        for s in range(n_samples):
            code = generate.solve(model, tok, p["prompt"], max_new=max_new,
                                  temperature=temperature if s else 0.0, seed=s)
            jobs.append((p["id"], code, p["tests"]))
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda j: run_tests_on(j[1], j[2], timeout=5)["ok"], jobs))
    per: dict[str, list[bool]] = {}
    for (pid, _, _), ok in zip(jobs, res):
        per.setdefault(pid, []).append(ok)
    p1 = float(np.mean([pass_at_k(len(v), sum(v), 1) for v in per.values()]))
    p5 = float(np.mean([pass_at_k(len(v), sum(v), min(5, len(v))) for v in per.values()]))
    example = next((j[1] for j in jobs), "")
    return {"problems": len(per), "samples": n_samples, "pass@1": round(p1, 4), "pass@5": round(p5, 4),
            "solved_any": sum(any(v) for v in per.values()), "example_completion": example[:400]}


@torch.no_grad()
def lm_score(model, tok, text: str) -> float:
    ids = tok.encode(text)[: model.cfg.seq_len * 2]
    if len(ids) < 2:
        return 0.0
    x = torch.tensor([ids])
    _, loss = model(x[:, :-1], x[:, 1:])
    return float(loss)


def bugfix(model, tok, evalsets: Path, fname: str = "bugfix.jsonl", use_lm: bool = True) -> dict:
    rows = load(Path(evalsets) / fname)
    lm_only = search = 0
    tries = []
    for b in rows:
        run = lambda c, b=b: run_tests_on(c, b["tests"], timeout=5)  # noqa: E731
        if model is not None and use_lm:
            prompt = f"<|fix|>{b['buggy']}<|test|>{chr(10).join(b['tests'])}\n<|assistant|>"
            cand = generate.complete(model, tok, prompt, max_new=96, temperature=0.0)
            if run(cand)["ok"]:
                lm_only += 1
        scorer = (lambda c: lm_score(model, tok, c)) if (model is not None and use_lm) else None
        r = repair.repair(b["buggy"], run, scorer=scorer)
        search += r["ok"]
        tries.append(r["tries"])
    return {"cases": len(rows), "lm_only_fixed": lm_only, "repair_fixed": search,
            "repair_rate": round(search / max(len(rows), 1), 4), "lm_only_rate": round(lm_only / max(len(rows), 1), 4),
            "median_tries": float(np.median(tries)) if tries else 0}


@torch.no_grad()
def perplexity(model, tok, evalsets: Path) -> dict:
    rows = load(Path(evalsets) / "ppl_heldout.jsonl")
    T = model.cfg.seq_len
    tot_loss, tot_tok = 0.0, 0
    per = {}
    for r in rows:
        ids = tok.encode(r["text"]) + [tok.eot]
        l_sum, n = 0.0, 0
        for s in range(0, len(ids) - 1, T):
            chunk = ids[s:s + T + 1]
            if len(chunk) < 2:
                continue
            x = torch.tensor([chunk])
            _, loss = model(x[:, :-1], x[:, 1:])
            k = len(chunk) - 1
            l_sum += float(loss) * k
            n += k
        per[r["id"]] = round(math.exp(l_sum / max(n, 1)), 2)
        tot_loss += l_sum
        tot_tok += n
    bpc_chars = sum(len(r["text"]) for r in rows)
    return {"ppl": round(math.exp(tot_loss / max(tot_tok, 1)), 3), "tokens": tot_tok,
            "bits_per_char": round(tot_loss / math.log(2) / max(bpc_chars, 1), 4), "per_doc": per}
