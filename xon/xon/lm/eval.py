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


def bugfix(model, tok, evalsets: Path, fname: str = "bugfix.jsonl", use_lm: bool = True, pretrained=None) -> dict:
    rows = load(Path(evalsets) / fname)
    lang = rows[0].get("lang", "python") if rows else "python"
    lm_only = search = 0
    tries = []
    for b in rows:
        if lang == "cpp":
            from xon.agent.sandbox import run_cpp_tests
            run = lambda c, b=b: run_cpp_tests(c, b["tests"], timeout=5)  # noqa: E731
        else:
            run = lambda c, b=b: run_tests_on(c, b["tests"], timeout=5)  # noqa: E731
        if model is not None and use_lm and lang == "python":
            prompt = f"<|fix|>{b['buggy']}<|test|>{chr(10).join(b['tests'])}\n<|assistant|>"
            cand = generate.complete(model, tok, prompt, max_new=96, temperature=0.0)
            if run(cand)["ok"]:
                lm_only += 1
        scorer = (lambda c: lm_score(model, tok, c)) if (model is not None and use_lm) else None
        tests_txt = "\n".join(b["tests"])
        rewriter = (lambda code, err, t=tests_txt: pretrained.rewrite(code, err, lang=lang, tests=t, n=4)) if pretrained else None
        r = repair.repair(b["buggy"], run, scorer=scorer, lang=lang, rewriter=rewriter)
        stages = locals().setdefault("stages", {})
        if r["ok"]:
            stages[r.get("stage", "mutation")] = stages.get(r.get("stage", "mutation"), 0) + 1
        search += r["ok"]
        tries.append(r["tries"])
    return {"cases": len(rows), "lm_only_fixed": lm_only, "repair_fixed": search,
            "repair_rate": round(search / max(len(rows), 1), 4), "lm_only_rate": round(lm_only / max(len(rows), 1), 4),
            "median_tries": float(np.median(tries)) if tries else 0, "fixed_by_stage": locals().get("stages", {})}


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


def pass_k_with(solve, problems: list[dict], runner, n_samples: int = 5) -> dict:
    """solve(problem, n) -> list of n candidate programs (first one greedy). runner(code, tests) -> {'ok': bool}."""
    per, examples = {}, []
    jobs = []
    for p in problems:
        cands = solve(p, n_samples)
        examples.append(cands[0])
        jobs += [(p["id"], c, p["tests"]) for c in cands]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda j: runner(j[1], j[2])["ok"], jobs))
    for (pid, _, _), ok in zip(jobs, res):
        per.setdefault(pid, []).append(ok)
    k5 = lambda v: pass_at_k(len(v), sum(v), min(5, len(v)))  # noqa: E731
    return {"problems": len(per), "samples": n_samples,
            "pass@1": round(float(np.mean([pass_at_k(len(v), sum(v), 1) for v in per.values()])), 4),
            "greedy_solved": sum(v[0] for v in per.values()),
            "pass@5": round(float(np.mean([k5(v) for v in per.values()])), 4),
            "solved_any": sum(any(v) for v in per.values()), "example": examples[0][:400] if examples else ""}


def cpp_pass_k(model, tok, evalsets: Path, n_samples: int = 5, limit: int | None = None) -> dict:
    from xon.agent.sandbox import run_cpp_tests
    probs = load(Path(evalsets) / "cpp_problems.jsonl")[:limit]
    solve = lambda p, n: [generate.solve_cpp(model, tok, p["prompt"], temperature=0.8 if s else 0.0, seed=s) for s in range(n)]  # noqa: E731
    return pass_k_with(solve, probs, lambda c, t: run_cpp_tests(c, t, timeout=5), n_samples)


def pretrained_eval(coder, evalsets: Path, n_samples: int = 5, limit: int | None = None) -> dict:
    """Python + C++ pass@k and bug-fix rewrite rate for the warm-start model."""
    from xon.agent.sandbox import run_cpp_tests
    py = load(Path(evalsets) / "code_problems.jsonl")[:limit]
    cpp = load(Path(evalsets) / "cpp_problems.jsonl")[:limit]

    def s_py(p, n):
        out = coder.solve_python(p["prompt"], 1, 0.0)
        return out + (coder.solve_python(p["prompt"], n - 1, 0.8) if n > 1 else [])

    def s_cpp(p, n):
        out = coder.solve_cpp(p["prompt"], 1, 0.0)
        return out + (coder.solve_cpp(p["prompt"], n - 1, 0.8) if n > 1 else [])

    res = {"model": coder.name, "license": coder.license,
           "python": pass_k_with(s_py, py, lambda c, t: run_tests_on(c, t, timeout=5), n_samples),
           "cpp": pass_k_with(s_cpp, cpp, lambda c, t: run_cpp_tests(c, t, timeout=5), n_samples)}
    for fname in ("bugfix.jsonl", "bugfix_blind.jsonl"):
        rows = load(Path(evalsets) / fname)
        ok = 0
        for b in rows:
            r0 = run_tests_on(b["buggy"], b["tests"], timeout=5)
            cands = coder.rewrite(b["buggy"], r0.get("stderr", ""), tests="\n".join(f"assert {t}" for t in b["tests"]), n=4)
            ok += any(run_tests_on(c, b["tests"], timeout=5)["ok"] for c in cands)
        res[fname.split(".")[0] + "_rewrite_rate@4"] = round(ok / len(rows), 4)
    return res
