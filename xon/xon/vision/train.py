"""Vision training: image-text contrastive + classification (weak/pseudo labels) + UI detection."""
from __future__ import annotations

import random
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from xon import config
from xon.datasets.shapes import SHAPES
from xon.trainer.recover import FaultInjector, Preemption, bad_loss, is_oom, load_ckpt, save_ckpt
from xon.vision.model import VisionConfig, XONVision
from xon.vision.ui_detect import DET_H, DET_W, det_loss, encode_targets

log = config.log("vision")
MEAN = torch.tensor([0.5, 0.5, 0.5]).view(3, 1, 1)


def to_tensor(img: Image.Image, size: tuple[int, int] | None = None) -> torch.Tensor:
    if size and img.size != size:
        img = img.resize(size, Image.BILINEAR)
    a = torch.from_numpy(np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1)
    return a - MEAN


def train(pairs: list[dict], ui: list[dict], out_dir: Path, *, minutes: float = 4.0, max_steps: int = 3000,
          cfg: VisionConfig | None = None, lr: float = 2e-3, batch: int = 64, det_batch: int = 8, seed: int = 0,
          init_from: Path | None = None, inject: dict | None = None, gov=None, log_path: Path | None = None) -> dict:
    """pairs: [{'image': PIL 64x64, 'caption': str, 'label': int|None}]; ui: [{'image': PIL, 'boxes': [...]}]."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    rng = random.Random(seed)
    cfg = cfg or VisionConfig(n_classes=len(SHAPES))
    model = XONVision(cfg)
    if init_from and Path(init_from).exists():
        st = load_ckpt(init_from)
        model.load_state_dict(st["model"])
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    X = torch.stack([to_tensor(p["image"], (64, 64)) for p in pairs]) if pairs else None
    caps = [p["caption"] for p in pairs]
    labels = torch.tensor([p["label"] if p.get("label") is not None else -1 for p in pairs])
    lab_idx = (labels >= 0).nonzero().flatten().tolist()
    U = [to_tensor(u["image"], (DET_W, DET_H)) for u in ui]
    T = [encode_targets(u["boxes"], u["image"].size[0], u["image"].size[1]) for u in ui]
    faults = FaultInjector(inject)
    log_path = Path(log_path) if log_path else out_dir / "vision_log.jsonl"
    t0, step, events = time.time(), 0, []
    model.train()
    with Preemption() as pre:
        while step < max_steps and (time.time() - t0) / 60 < minutes:
            if gov is not None:
                gov.tick()
            cur_lr = lr * 0.5 * (1 + np.cos(np.pi * min(1.0, (time.time() - t0) / (minutes * 60))))
            for g in opt.param_groups:
                g["lr"] = max(cur_lr, lr * 0.05)
            try:
                if faults.check(step, "oom"):
                    raise RuntimeError("out of memory (injected)")
                loss = torch.zeros(())
                parts = {}
                if X is not None and len(pairs) >= 4:
                    idx = rng.sample(range(len(pairs)), min(batch, len(pairs)))
                    xb = X[idx]
                    # augmentation: brightness jitter + horizontal flip (shapes are flip-invariant in class)
                    xb = xb * (1 + 0.2 * (torch.rand(len(idx), 1, 1, 1) - 0.5))
                    if rng.random() < 0.5:
                        xb = xb.flip(-1)
                    lc = model.contrastive_loss(xb, [caps[i] for i in idx])
                    parts["clip"] = lc.item()
                    loss = loss + lc
                    li = [i for i in idx if labels[i] >= 0]
                    if lab_idx:
                        li = rng.sample(lab_idx, min(batch, len(lab_idx)))
                        lcls = torch.nn.functional.cross_entropy(model.classify(X[li]), labels[li])
                        parts["cls"] = lcls.item()
                        loss = loss + lcls
                if U:
                    di = rng.sample(range(len(U)), min(det_batch, len(U)))
                    out = model.detect_raw(torch.stack([U[i] for i in di]))
                    ld = det_loss(out, torch.stack([T[i][0] for i in di]), torch.stack([T[i][1] for i in di]))
                    parts["det"] = ld.item()
                    loss = loss + ld
                if faults.check(step, "nan"):
                    loss = loss * float("nan")
                if bad_loss(loss):
                    raise FloatingPointError
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
                opt.step()
            except FloatingPointError:
                lr *= 0.5
                opt.zero_grad(set_to_none=True)
                events.append({"event": "nan_skip", "step": step, "new_lr": lr})
                continue
            except RuntimeError as e:
                if not is_oom(e):
                    raise
                batch, det_batch = max(4, batch // 2), max(1, det_batch // 2)
                events.append({"event": "oom_recovered", "batch": batch, "det_batch": det_batch})
                continue
            step += 1
            if step % 25 == 0 or step == 1:
                config.jsonl_append(log_path, {"step": step, "loss": round(loss.item(), 4), **{k: round(v, 4) for k, v in parts.items()}})
            if pre.flag:
                events.append({"event": "preempted", "step": step})
                break
    model.eval()
    save_ckpt(out_dir / "vision.pt", model=model.state_dict(), cfg=cfg.to_dict(), step=step, classes=SHAPES)
    return {"step": step, "minutes": round((time.time() - t0) / 60, 2), "params": model.n_params(), "events": events,
            "pairs": len(pairs), "labeled": len(lab_idx), "ui_samples": len(ui)}


def load_model(path: Path) -> XONVision:
    st = load_ckpt(path)
    m = XONVision(VisionConfig.from_dict(st["cfg"]))
    m.load_state_dict(st["model"])
    return m.eval()
