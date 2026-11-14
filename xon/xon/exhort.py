"""Exhort: find neurons that are dead, broken or useless, delete them, and reincarnate them better.

A "neuron" here is one hidden unit of a feed-forward block: one row of the layer(s) that produce it and one
column of the layer that reads it. In the XON LM that is one SwiGLU unit (row j of w1 and w3, column j of w2);
in a plain MLP / conv head it is one output row (or channel) of the first layer and the matching input column of
the next.

Diagnosis (on a calibration batch, no training):
  broken   any NaN/inf in its weights, or its activation is non-finite
  dead     it (almost) never fires: mean |activation| below `dead_rel` x the layer's median
  useless  it fires but changes nothing: activation x outgoing-weight norm in the bottom `useless_q` of the layer
           (only taken once `useless_q` > 0, and never more than `max_frac` of a layer in total)

Reincarnation (the "better" part, gradient-guided rebirth):
  1. delete: the unit's incoming row(s), bias and outgoing column are wiped
  2. try `candidates` fresh random incoming rows (scaled to match the healthy neurons of that layer) and keep the
     one whose outgoing column has the largest loss gradient, i.e. the newborn neuron that can help the most
  3. outgoing column starts at zero (the network's output is unchanged at birth), then one small step along
     -gradient so the neuron starts doing something useful right away
  4. a short heal-train (`heal_steps`) with optimizer state reset, then the validation loss is compared with the
     loss before Exhort: if it got worse by more than `tolerance`, everything is rolled back

Nothing is promoted by Exhort itself: in the training cycle the promotion gate still decides.
"""
from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable

import torch
import torch.nn as nn

LossFn = Callable[[nn.Module, object], torch.Tensor]


@dataclass
class ExhortConfig:
    dead_rel: float = 0.02  # dead if mean |act| < dead_rel * median of the layer
    useless_q: float = 0.02  # bottom quantile of contribution counted as useless (0 = off)
    max_frac: float = 0.10  # never reincarnate more than this share of one layer per run
    candidates: int = 4  # random rebirths tried per neuron; the most useful one wins
    birth_step: float = 0.05  # size of the first step of the new outgoing column (relative to healthy columns)
    heal_steps: int = 60
    heal_lr: float = 1e-3
    tolerance: float = 0.0  # allowed val-loss increase before rollback (absolute)
    seed: int = 87

    @classmethod
    def from_dict(cls, d: dict | None) -> "ExhortConfig":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in (d or {}).items() if k in keys})


@dataclass
class Group:
    """One layer of neurons: producers make the hidden units (dim 0), the consumer reads them (dim 1)."""
    name: str
    producers: list[nn.Module]
    consumer: nn.Module

    @property
    def size(self) -> int:
        return self.producers[0].weight.shape[0]


@dataclass
class LayerReport:
    name: str
    size: int
    broken: list[int] = field(default_factory=list)
    dead: list[int] = field(default_factory=list)
    useless: list[int] = field(default_factory=list)
    mean_act: float = 0.0

    @property
    def targets(self) -> list[int]:
        return sorted(set(self.broken) | set(self.dead) | set(self.useless))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["targets"] = self.targets
        return d


_ACTS = (nn.ReLU, nn.GELU, nn.SiLU, nn.Tanh, nn.Sigmoid, nn.LeakyReLU, nn.ELU, nn.Mish)
_LAYERS = (nn.Linear, nn.Conv1d, nn.Conv2d)


def find_groups(model: nn.Module) -> list[Group]:
    """XON LM SwiGLU blocks, plus every Sequential(layer, activation, layer) pair (MLPs, conv heads)."""
    groups: list[Group] = []
    for name, m in model.named_modules():
        if all(hasattr(m, k) for k in ("w1", "w2", "w3")) and isinstance(m.w2, nn.Linear):
            groups.append(Group(name or "ffn", [m.w1, m.w3], m.w2))
        elif isinstance(m, nn.Sequential):
            mods = list(m)
            for i in range(len(mods) - 2):
                a, act, b = mods[i], mods[i + 1], mods[i + 2]
                if isinstance(a, _LAYERS) and isinstance(act, _ACTS) and isinstance(b, _LAYERS) \
                        and a.weight.shape[0] == b.weight.shape[1]:
                    groups.append(Group(f"{name}.{i}" if name else str(i), [a], b))
    return groups


class _Probe:
    """Records the input of each consumer (= the hidden activations) during one forward pass."""

    def __init__(self, groups: list[Group]):
        self.acts: dict[str, list[torch.Tensor]] = {g.name: [] for g in groups}
        self.handles = []
        for g in groups:
            conv = isinstance(g.consumer, (nn.Conv1d, nn.Conv2d))
            self.handles.append(g.consumer.register_forward_pre_hook(self._hook(g.name, conv)))

    def _hook(self, name: str, conv: bool):
        def fn(_mod, inp):
            h = inp[0].detach().float()
            if conv:
                stat = h.abs().transpose(0, 1).reshape(h.shape[1], -1).mean(1)
                fin = torch.isfinite(h).transpose(0, 1).reshape(h.shape[1], -1).all(1)
            else:
                stat = h.abs().reshape(-1, h.shape[-1]).mean(0)
                fin = torch.isfinite(h).reshape(-1, h.shape[-1]).all(0)
            self.acts[name].append(torch.where(fin, stat, torch.full_like(stat, float("nan"))))
        return fn

    def close(self):
        for h in self.handles:
            h.remove()


def diagnose(model: nn.Module, batches: Iterable, loss_fn: LossFn, cfg: ExhortConfig | None = None,
             groups: list[Group] | None = None) -> list[LayerReport]:
    cfg = cfg or ExhortConfig()
    groups = groups if groups is not None else find_groups(model)
    probe = _Probe(groups)
    was = model.training
    model.eval()
    try:
        with torch.no_grad():
            for b in batches:
                loss_fn(model, b)
    finally:
        probe.close()
        model.train(was)
    out = []
    for g in groups:
        rep = LayerReport(g.name, g.size)
        stats = probe.acts[g.name]
        act = torch.stack(stats).mean(0) if stats else torch.zeros(g.size)
        bad_w = torch.zeros(g.size, dtype=torch.bool)
        for p in g.producers:
            w = p.weight.detach().reshape(g.size, -1)
            bad_w |= ~torch.isfinite(w).all(1).cpu()
            if getattr(p, "bias", None) is not None:
                bad_w |= ~torch.isfinite(p.bias.detach()).cpu()
        cw = g.consumer.weight.detach()
        cw = cw.transpose(0, 1).reshape(g.size, -1)
        bad_w |= ~torch.isfinite(cw).all(1).cpu()
        act = act.cpu()
        broken = bad_w | ~torch.isfinite(act)
        rep.broken = torch.nonzero(broken).flatten().tolist()
        healthy = ~broken
        if healthy.sum() == 0:
            out.append(rep)
            continue
        med = act[healthy].median().item()
        rep.mean_act = float(act[healthy].mean())
        dead = healthy & (act < cfg.dead_rel * max(med, 1e-12))
        rep.dead = torch.nonzero(dead).flatten().tolist()
        budget = max(0, int(cfg.max_frac * g.size) - len(rep.broken) - len(rep.dead))
        if cfg.useless_q > 0 and budget > 0:
            contrib = act * torch.nan_to_num(cw.float().norm(dim=1).cpu(), nan=0.0)
            alive = healthy & ~dead
            if alive.sum() > 4:
                thr = torch.quantile(contrib[alive], cfg.useless_q).item()
                cand = [i for i in torch.argsort(contrib).tolist() if alive[i] and contrib[i] <= thr]
                rep.useless = cand[:budget]
        # cap dead too (broken are always fixed: they poison everything downstream)
        cap = max(1, int(cfg.max_frac * g.size))
        if len(rep.broken) + len(rep.dead) > cap:
            rep.dead = rep.dead[:max(0, cap - len(rep.broken))]
        out.append(rep)
    return out


def _healthy_scale(p: nn.Module, keep: torch.Tensor) -> float:
    w = p.weight.detach().reshape(p.weight.shape[0], -1)
    w = w[keep]
    w = w[torch.isfinite(w).all(1)]
    return float(w.std()) if w.numel() > 1 else 0.02


def reincarnate(model: nn.Module, reports: list[LayerReport], batches: list, loss_fn: LossFn,
                cfg: ExhortConfig | None = None, groups: list[Group] | None = None) -> dict:
    """Delete + rebirth every targeted neuron (gradient-guided). Returns counts per layer."""
    cfg = cfg or ExhortConfig()
    groups = {g.name: g for g in (groups if groups is not None else find_groups(model))}
    gen = torch.Generator().manual_seed(cfg.seed)
    reborn: dict[str, int] = {}
    calib = batches[:2] if batches else []
    plan = []
    # 1. delete every bad neuron in the whole network first, so one broken layer cannot poison the
    #    gradients used to choose the rebirths of another
    for rep in reports:
        targets = rep.targets
        if not targets or rep.name not in groups:
            continue
        g = groups[rep.name]
        dev = g.consumer.weight.device
        idx = torch.tensor(targets, device=dev)
        keep = torch.ones(g.size, dtype=torch.bool)
        keep[targets] = False
        scales = [_healthy_scale(p, keep.to(p.weight.device)) for p in g.producers]
        cw = g.consumer.weight.detach().transpose(0, 1).reshape(g.size, -1)
        good = cw[keep.to(dev)]
        good = good[torch.isfinite(good).all(1)]
        col_scale = float(good.norm(dim=1).mean()) if len(good) else 0.02
        with torch.no_grad():
            for p in g.producers:
                p.weight[idx] = 0
                if getattr(p, "bias", None) is not None:
                    p.bias[idx] = 0
            g.consumer.weight[:, idx] = 0
        plan.append((rep, g, idx, targets, scales, col_scale))
    for rep, g, idx, targets, scales, col_scale in plan:
        best_score = torch.full((len(targets),), -1.0)
        best_rows: list[torch.Tensor | None] = [None] * len(g.producers)
        best_grad = None
        for _ in range(max(1, cfg.candidates)):  # 2. candidates
            rows = []
            with torch.no_grad():
                for p, s in zip(g.producers, scales):
                    shape = (len(targets),) + tuple(p.weight.shape[1:])
                    r = (torch.randn(shape, generator=gen) * s).to(p.weight.device, p.weight.dtype)
                    p.weight[idx] = r
                    rows.append(r)
            model.zero_grad(set_to_none=True)
            for b in calib:
                loss_fn(model, b).backward()
            gcol = g.consumer.weight.grad
            if gcol is None:
                continue
            gsel = torch.nan_to_num(gcol.detach()[:, idx].transpose(0, 1).reshape(len(targets), -1), nan=0.0, posinf=0.0, neginf=0.0)
            score = torch.nan_to_num(gsel.float().norm(dim=1), nan=-1.0).cpu()
            better = score > best_score
            for k in range(len(g.producers)):
                if best_rows[k] is None:
                    best_rows[k] = rows[k].clone()
                else:
                    best_rows[k][better.to(rows[k].device)] = rows[k][better.to(rows[k].device)]
            if best_grad is None:
                best_grad = gsel.clone()
            else:
                best_grad[better.to(gsel.device)] = gsel[better.to(gsel.device)]
            best_score = torch.maximum(best_score, score)
        model.zero_grad(set_to_none=True)
        with torch.no_grad():  # 3. install the winners, outgoing column = one small step down the gradient
            for p, r in zip(g.producers, best_rows):
                if r is not None:
                    p.weight[idx] = r
            if best_grad is not None:
                gn = best_grad.float().norm(dim=1, keepdim=True).clamp(min=1e-12)
                step = (-best_grad.float() / gn * (cfg.birth_step * col_scale)).to(g.consumer.weight.dtype)
                col_shape = (g.consumer.weight.shape[0],) + tuple(g.consumer.weight.shape[2:])
                for n, j in enumerate(targets):
                    g.consumer.weight[:, j] = step[n].reshape(col_shape)
        reborn[rep.name] = len(targets)
    return reborn


def heal(model: nn.Module, batches: list, loss_fn: LossFn, steps: int, lr: float) -> list[float]:
    if steps <= 0 or not batches:
        return []
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
    model.train()
    hist = []
    for s in range(steps):
        loss = loss_fn(model, batches[s % len(batches)])
        if not torch.isfinite(loss):
            break
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        hist.append(float(loss.detach()))
    return hist


def _mean_loss(model: nn.Module, batches: list, loss_fn: LossFn) -> float:
    was = model.training
    model.eval()
    with torch.no_grad():
        v = [float(loss_fn(model, b)) for b in batches]
    model.train(was)
    v = [x for x in v if math.isfinite(x)]
    return sum(v) / len(v) if v else float("inf")


def exhort(model: nn.Module, train_batches: list, val_batches: list, loss_fn: LossFn,
           cfg: ExhortConfig | None = None, dry_run: bool = False) -> dict:
    """Diagnose -> reincarnate -> heal -> keep only if validation did not get worse. Mutates `model` in place."""
    cfg = cfg or ExhortConfig()
    torch.manual_seed(cfg.seed)
    groups = find_groups(model)
    reports = diagnose(model, train_batches[:4], loss_fn, cfg, groups)
    found = sum(len(r.targets) for r in reports)
    total = sum(r.size for r in reports)
    res = {"layers": [r.to_dict() for r in reports], "neurons": total, "found": found,
           "broken": sum(len(r.broken) for r in reports), "dead": sum(len(r.dead) for r in reports),
           "useless": sum(len(r.useless) for r in reports), "reborn": 0, "kept": False, "dry_run": dry_run}
    # sanitize first so a broken neuron cannot make the "before" loss infinite forever
    before = _mean_loss(model, val_batches, loss_fn)
    res["val_before"] = before
    if dry_run or found == 0:
        res["val_after"] = before
        res["reason"] = "dry run" if dry_run else "every neuron is healthy"
        return res
    snapshot = copy.deepcopy(model.state_dict())
    reborn = reincarnate(model, reports, train_batches, loss_fn, cfg, groups)
    res["reborn"] = sum(reborn.values())
    res["val_at_birth"] = _mean_loss(model, val_batches, loss_fn)
    res["heal_loss"] = heal(model, train_batches, loss_fn, cfg.heal_steps, cfg.heal_lr)[-5:]
    after = _mean_loss(model, val_batches, loss_fn)
    res["val_after"] = after
    if not math.isfinite(before):
        ok = math.isfinite(after)  # it was broken before: any finite loss is an improvement
    else:
        ok = after <= before + cfg.tolerance
    if ok:
        res["kept"] = True
        res["reason"] = f"val loss {before:.4f} -> {after:.4f}"
    else:
        model.load_state_dict(snapshot)
        res["reason"] = f"rolled back: val loss would go {before:.4f} -> {after:.4f}"
    return res


# ----------------------------------------------------------------------------- XON LM helpers

def lm_loss(model, batch):
    x, y = batch
    return model(x, y)[1]


def lm_batches(ids, seq_len: int, n: int, batch: int = 8, seed: int = 0, device: str = "cpu") -> list:
    import numpy as np
    if len(ids) < seq_len + 2:
        return []
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        st = rng.integers(0, len(ids) - seq_len - 1, size=batch)
        a = torch.from_numpy(np.stack([ids[s:s + seq_len + 1] for s in st]).astype("int64")).to(device)
        out.append((a[:, :-1], a[:, 1:]))
    return out


def exhort_lm_checkpoint(path_in, train_ids, val_ids, path_out=None, cfg: ExhortConfig | None = None,
                         dry_run: bool = False, device: str = "cpu") -> dict:
    """Run Exhort on a saved XON LM checkpoint (model.pt / lm.pt). Writes path_out only when kept."""
    from pathlib import Path

    from xon.lm.model import LMConfig, XONLM
    from xon.trainer.recover import load_ckpt, save_ckpt
    cfg = cfg or ExhortConfig()
    st = load_ckpt(Path(path_in))
    lmcfg = LMConfig.from_dict(st["cfg"])
    model = XONLM(lmcfg).to(device)
    model.load_state_dict(st["model"])
    seq = min(lmcfg.seq_len, 128)
    tr = lm_batches(train_ids, seq, max(8, cfg.heal_steps), seed=cfg.seed, device=device)
    va = lm_batches(val_ids if len(val_ids) > seq + 2 else train_ids, seq, 6, seed=cfg.seed + 1, device=device)
    res = exhort(model, tr, va, lm_loss, cfg, dry_run=dry_run)
    if res["kept"] and not dry_run:
        out = Path(path_out or path_in)
        extra = {k: v for k, v in st.items() if k not in ("model",)}
        extra["exhort"] = {k: res[k] for k in ("found", "reborn", "val_before", "val_after")}
        save_ckpt(out, model=model.state_dict(), **extra)
        res["saved"] = str(out)
    return res


def exhort_promoted(xcfg: dict, *, dry_run: bool = False, apply: bool = False, checkpoint=None,
                    overrides: dict | None = None) -> dict:
    """`xon exhort`: run on the promoted XON LM with the replay buffer as data.
    Writes checkpoints/exhort/lm.pt; with apply=True also replaces promoted/lm.pt (old one kept as lm.pre-exhort.pt)."""
    import shutil
    from pathlib import Path

    from xon import config
    from xon.lm import data as lmdata
    from xon.tokenizer import BPETokenizer
    from xon.trainer.replay import Replay
    ck = config.path(xcfg, "checkpoints")
    src = Path(checkpoint) if checkpoint else ck / "promoted" / "lm.pt"
    tokp = ck / "promoted" / "tokenizer.json"
    if not src.exists() or not tokp.exists():
        return {"ok": False, "error": f"no trained XON LM at {src}; run `xon train --quick` first"}
    recs = Replay(ck / "replay.json").items
    if not recs:
        return {"ok": False, "error": "no training data in the replay buffer; run `xon train --quick` first"}
    tr, va = lmdata.tokenize(recs, BPETokenizer.load(tokp), seed=1)
    cfg = ExhortConfig.from_dict({**xcfg.get("exhort", {}), **(overrides or {})})
    out = ck / "exhort" / "lm.pt"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    res = exhort_lm_checkpoint(out, tr, va, out, cfg, dry_run=dry_run)
    res["ok"] = True
    res["checkpoint"] = str(src)
    if apply and res.get("kept") and not dry_run and checkpoint is None:
        shutil.copy2(src, src.with_name("lm.pre-exhort.pt"))
        shutil.copy2(out, src)
        res["applied"] = str(src)
    config.jsonl_append(config.path(xcfg, "logs") / "exhort.jsonl",
                        {k: res.get(k) for k in ("checkpoint", "neurons", "found", "broken", "dead", "useless", "reborn",
                                                 "kept", "val_before", "val_after", "reason", "applied")})
    return res
