"""UI-element detection: target encoding, loss, decoding (+NMS) and IoU matching."""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from xon.datasets.synth_ui import UI_CLASSES

DET_W, DET_H = 320, 240  # detector input size (screenshots are 640x480)


def encode_targets(boxes: list[dict], src_w: int, src_h: int, stride: int = 8):
    gw, gh = DET_W // stride, DET_H // stride
    cls = torch.zeros(gh, gw, dtype=torch.long)  # 0 = background
    reg = torch.zeros(4, gh, gw)
    area = torch.full((gh, gw), float("inf"))
    sx, sy = DET_W / src_w, DET_H / src_h
    for b in boxes:
        if b["label"] not in UI_CLASSES:
            continue
        x, y, w, h = b["x"] * sx, b["y"] * sy, b["w"] * sx, b["h"] * sy
        cx, cy = x + w / 2, y + h / 2
        a = w * h
        # center sampling: every cell whose center lies in the middle third of the box (max 3x3 around center)
        gcx, gcy = int(cx // stride), int(cy // stride)
        rx = max(0, min(1, int(w / 3 // stride)))
        ry = max(0, min(1, int(h / 3 // stride)))
        for gy in range(gcy - ry, gcy + ry + 1):
            for gx in range(gcx - rx, gcx + rx + 1):
                if not (0 <= gx < gw and 0 <= gy < gh):
                    continue
                if a >= area[gy, gx]:  # smaller object wins the cell (icons inside cards/buttons)
                    continue
                area[gy, gx] = a
                cls[gy, gx] = UI_CLASSES.index(b["label"]) + 1
                reg[:, gy, gx] = torch.tensor([cx / stride - gx, cy / stride - gy, np.log(max(w, 1) / stride),
                                               np.log(max(h, 1) / stride)])
    return cls, reg


def det_loss(out, cls_t, reg_t, bg_weight: float = 0.1):
    n = out.shape[1] - 4
    logits, reg = out[:, :n], out[:, n:]
    w = torch.ones(n, device=out.device)
    w[0] = bg_weight
    lc = F.cross_entropy(logits, cls_t, weight=w)
    pos = cls_t > 0
    if pos.any():
        lr = F.smooth_l1_loss(reg.permute(0, 2, 3, 1)[pos], reg_t.permute(0, 2, 3, 1)[pos])
    else:
        lr = out.sum() * 0
    return lc + lr


def iou(a, b) -> float:
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0, min(ax2, bx2) - max(a[0], b[0])), max(0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    u = a[2] * a[3] + b[2] * b[3] - inter
    return inter / u if u > 0 else 0.0


def decode(out, src_w: int, src_h: int, stride: int = 8, thresh: float = 0.35, nms_iou: float = 0.5) -> list[dict]:
    """out: (C, gh, gw) for one image -> list of boxes in source pixels."""
    n = out.shape[0] - 4
    prob = torch.softmax(out[:n], 0)
    reg = out[n:]
    score, c = prob[1:].max(0)
    sx, sy = src_w / DET_W, src_h / DET_H
    dets = []
    ys, xs = torch.nonzero(score > thresh, as_tuple=True)
    for gy, gx in zip(ys.tolist(), xs.tolist()):
        dx, dy, lw, lh = reg[:, gy, gx].tolist()
        cx, cy = (gx + dx) * stride, (gy + dy) * stride
        w, h = float(np.exp(lw)) * stride, float(np.exp(lh)) * stride
        dets.append({"label": UI_CLASSES[int(c[gy, gx])], "score": float(score[gy, gx]),
                     "x": (cx - w / 2) * sx, "y": (cy - h / 2) * sy, "w": w * sx, "h": h * sy})
    dets.sort(key=lambda d: -d["score"])
    keep = []
    for d in dets:
        if all(not (k["label"] == d["label"] and iou(_xywh(k), _xywh(d)) > nms_iou) for k in keep):
            keep.append(d)
    return keep


def _xywh(d):
    return (d["x"], d["y"], d["w"], d["h"])


def match(preds: list[dict], gts: list[dict], thr: float = 0.5) -> dict:
    used = set()
    tp = 0
    per = {c: {"tp": 0, "fp": 0, "fn": 0} for c in UI_CLASSES}
    for p in preds:
        best, bj = 0.0, -1
        for j, g in enumerate(gts):
            if j in used or g["label"] != p["label"]:
                continue
            v = iou(_xywh(p), _xywh(g))
            if v > best:
                best, bj = v, j
        if best >= thr:
            used.add(bj)
            tp += 1
            per[p["label"]]["tp"] += 1
        else:
            per[p["label"]]["fp"] += 1
    for j, g in enumerate(gts):
        if j not in used and g["label"] in per:
            per[g["label"]]["fn"] += 1
    return {"tp": tp, "fp": len(preds) - tp, "fn": len(gts) - tp, "per_class": per}
