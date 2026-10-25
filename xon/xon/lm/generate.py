"""Sampling with KV-cache; fill-in-the-middle; task -> code."""
from __future__ import annotations

import torch

from xon.lm.model import XONLM
from xon.tokenizer import BPETokenizer


@torch.no_grad()
def generate_ids(model: XONLM, ids: list[int], max_new: int = 128, temperature: float = 0.8, top_k: int = 40,
                 stop: set[int] | None = None, seed: int | None = None) -> list[int]:
    dev = next(model.parameters()).device
    g = torch.Generator(device="cpu")
    if seed is not None:
        g.manual_seed(seed)
    maxlen = model.cfg.seq_len * 4 - 2
    ids = ids[-(model.cfg.seq_len * 2):]
    caches = model.new_caches()
    x = torch.tensor([ids], device=dev)
    logits, _ = model(x, caches=caches, pos=0)
    pos = len(ids)
    out: list[int] = []
    for _ in range(max_new):
        lg = logits[0, -1].float().cpu()
        if temperature <= 0:
            nxt = int(lg.argmax())
        else:
            lg = lg / temperature
            if top_k:
                v, _ = torch.topk(lg, min(top_k, lg.numel()))
                lg[lg < v[-1]] = -float("inf")
            nxt = int(torch.multinomial(torch.softmax(lg, -1), 1, generator=g))
        if stop and nxt in stop:
            break
        out.append(nxt)
        if pos >= maxlen:
            break
        logits, _ = model(torch.tensor([[nxt]], device=dev), caches=caches, pos=pos)
        pos += 1
    return out


def complete(model, tok: BPETokenizer, prompt: str, max_new: int = 128, temperature: float = 0.8, seed=None,
             stop_strings: tuple[str, ...] = ()) -> str:
    stops = {tok.eot, tok.special("<|endfile|>")}
    out = tok.decode(generate_ids(model, tok.encode(prompt), max_new, temperature, stop=stops, seed=seed), skip_special=True)
    for s in stop_strings:
        i = out.find(s)
        if i >= 0:
            out = out[:i]
    return out


def fill_in_middle(model, tok: BPETokenizer, prefix: str, suffix: str, max_new: int = 64, temperature: float = 0.2,
                   seed=None) -> str:
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
    stops = {tok.eot, tok.special("<|endfile|>"), tok.special("<|fim_prefix|>")}
    return tok.decode(generate_ids(model, tok.encode(prompt), max_new, temperature, stop=stops, seed=seed), skip_special=True)


def solve(model, tok: BPETokenizer, prompt_code: str, max_new: int = 160, temperature: float = 0.8, seed=None) -> str:
    """Complete a function given its signature + docstring; stop at the next top-level statement."""
    body = complete(model, tok, f"<|file|>solution.py\n{prompt_code}", max_new, temperature, seed=seed)
    lines = []
    for line in body.split("\n"):
        if line and not line.startswith((" ", "\t")) and lines:
            break
        lines.append(line)
    return prompt_code + "\n".join(lines).rstrip() + "\n"
