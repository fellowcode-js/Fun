"""LM training: AdamW, cosine+warmup, grad accumulation, clipping, mixed precision, throughput logging,
time-based + SIGTERM checkpoints, resume, OOM and NaN auto-recovery."""
from __future__ import annotations

import contextlib
import math
import time
from pathlib import Path

import numpy as np
import torch

from xon import config
from xon.lm.data import Batcher
from xon.lm.model import LMConfig, XONLM
from xon.trainer.recover import (CheckpointTimer, FaultInjector, Preemption, bad_loss, is_oom, load_ckpt,
                                 save_ckpt)
from xon.workstation.budget import device as pick_device

log = config.log("lm")


def lr_at(step: int, total: int, peak: float, warmup: int, floor: float = 0.1) -> float:
    if step < warmup:
        return peak * (step + 1) / warmup
    p = min(1.0, (step - warmup) / max(1, total - warmup))
    return peak * (floor + (1 - floor) * 0.5 * (1 + math.cos(math.pi * p)))


@torch.no_grad()
def evaluate_loss(model: XONLM, ids: np.ndarray, seq_len: int, max_batches: int = 20, batch: int = 8) -> float:
    if len(ids) < seq_len + 2:
        return float("nan")
    model.eval()
    dev = next(model.parameters()).device
    losses = []
    starts = list(range(0, len(ids) - seq_len - 1, seq_len))[: max_batches * batch]
    for i in range(0, len(starts), batch):
        chunk = starts[i:i + batch]
        x = torch.from_numpy(np.stack([ids[s:s + seq_len + 1] for s in chunk]).astype(np.int64)).to(dev)
        _, loss = model(x[:, :-1], x[:, 1:])
        losses.append(loss.item())
    model.train()
    return float(np.mean(losses)) if losses else float("nan")


def train(cfg: LMConfig, train_ids: np.ndarray, val_ids: np.ndarray, out_dir: Path, *, max_steps: int = 1000,
          max_minutes: float | None = None, batch: int = 16, accum: int = 1, lr: float = 3e-3, warmup: int = 50,
          weight_decay: float = 0.1, clip: float = 1.0, ckpt_minutes: float = 5.0, eval_every: int = 200,
          init_from: Path | None = None, resume: bool = True, seed: int = 1337, inject: dict | None = None,
          log_path: Path | None = None, gov=None, dev: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = dev or pick_device()
    torch.manual_seed(seed)
    model = XONLM(cfg).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.95), weight_decay=weight_decay)
    step, best_val, events = 0, float("inf"), []
    last = out_dir / "last.pt"
    good = out_dir / "good.pt"
    st = load_ckpt(last) if resume else None
    if st is None and init_from is not None:
        init = load_ckpt(init_from)
        if init:
            model.load_state_dict(init["model"], strict=False)
            events.append({"event": "init_from", "path": str(init_from)})
    if st is not None:
        model.load_state_dict(st["model"])
        opt.load_state_dict(st["opt"])
        step, best_val = st["step"], st.get("best_val", best_val)
        batch, accum, lr = st.get("batch", batch), st.get("accum", accum), st.get("lr", lr)
        if st.get("grad_checkpoint"):
            model.cfg.grad_checkpoint = True
        events.append({"event": "resumed", "step": step})
        log.info(f"resumed from step {step}")
    batcher = Batcher(train_ids, cfg.seq_len, batch, seed=seed + step)
    faults = FaultInjector(inject)
    timer = CheckpointTimer(ckpt_minutes)
    use_amp = dev == "cuda"
    amp = (lambda: torch.autocast("cuda", dtype=torch.bfloat16)) if use_amp else contextlib.nullcontext
    log_path = Path(log_path) if log_path else out_dir / "train_log.jsonl"
    t_start = time.time()
    tok_count, t_window = 0, time.time()

    def snapshot(path: Path):
        save_ckpt(path, model=model.state_dict(), opt=opt.state_dict(), step=step, best_val=best_val,
                  cfg=cfg.to_dict(), batch=batch, accum=accum, lr=lr, grad_checkpoint=model.cfg.grad_checkpoint)

    if not good.exists():
        snapshot(good)
    model.train()
    with Preemption() as pre:
        while step < max_steps:
            if gov is not None:
                gov.tick()
            if max_minutes is not None and (time.time() - t_start) / 60 > max_minutes:
                events.append({"event": "time_budget", "step": step})
                break
            cur_lr = lr_at(step, max_steps, lr, warmup)
            for g in opt.param_groups:
                g["lr"] = cur_lr
            try:
                if faults.check(step, "oom"):
                    raise RuntimeError("CUDA out of memory (injected)")
                total = 0.0
                for _ in range(accum):
                    x, y = batcher()
                    x, y = x.to(dev), y.to(dev)
                    with amp():
                        _, loss = model(x, y)
                    if faults.check(step, "nan"):
                        loss = loss * float("nan")
                    (loss / accum).backward()
                    total += loss.item() / accum
                if bad_loss(total):
                    raise FloatingPointError("nan loss")
                torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
                opt.step()
                opt.zero_grad(set_to_none=True)
            except FloatingPointError:
                opt.zero_grad(set_to_none=True)
                g_st = load_ckpt(good)
                model.load_state_dict(g_st["model"])
                opt.load_state_dict(g_st["opt"])
                step = g_st["step"]
                lr *= 0.5
                events.append({"event": "nan_rollback", "to_step": step, "new_lr": lr})
                log.warning(f"NaN loss: rolled back to step {step}, lr -> {lr:.2e}")
                continue
            except RuntimeError as e:
                if not is_oom(e):
                    raise
                opt.zero_grad(set_to_none=True)
                if dev == "cuda":
                    torch.cuda.empty_cache()
                if batch <= 1:
                    raise
                batch, accum = max(1, batch // 2), accum * 2
                model.cfg.grad_checkpoint = True
                batcher = Batcher(train_ids, cfg.seq_len, batch, seed=seed + step)
                events.append({"event": "oom_recovered", "batch": batch, "accum": accum, "grad_checkpoint": True})
                log.warning(f"OOM: batch -> {batch}, accum -> {accum}, gradient checkpointing on")
                continue
            step += 1
            tok_count += batch * accum * cfg.seq_len
            if step % 20 == 0 or step == 1:
                dt = max(time.time() - t_window, 1e-6)
                config.jsonl_append(log_path, {"step": step, "loss": round(total, 4), "lr": cur_lr,
                                               "tok_per_s": round(tok_count / dt), "batch": batch, "accum": accum})
                tok_count, t_window = 0, time.time()
            if faults.check(step, "sigterm"):
                pre.flag = True
            if step % eval_every == 0 or step == max_steps:
                v = evaluate_loss(model, val_ids, cfg.seq_len)
                config.jsonl_append(log_path, {"step": step, "val_loss": round(v, 4)})
                if not math.isnan(v) and v < best_val:
                    best_val = v
                snapshot(good)  # last known-good point for NaN rollback
            if timer.due():
                snapshot(last)
            if pre.flag:
                snapshot(last)
                events.append({"event": "preempted", "step": step})
                break
    snapshot(last)
    v = evaluate_loss(model, val_ids, cfg.seq_len)
    save_ckpt(out_dir / "model.pt", model=model.state_dict(), cfg=cfg.to_dict(), step=step, val_loss=v)
    return {"step": step, "val_loss": v, "events": events, "minutes": round((time.time() - t_start) / 60, 2),
            "params": model.n_params(), "tokens_seen": step * batch * accum * cfg.seq_len,
            "preempted": any(e["event"] == "preempted" for e in events)}


def load_model(path: Path, dev: str = "cpu") -> XONLM:
    st = load_ckpt(path)
    m = XONLM(LMConfig.from_dict(st["cfg"]))
    m.load_state_dict(st["model"])
    return m.to(dev).eval()
