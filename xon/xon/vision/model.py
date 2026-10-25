"""XON vision net: ResNet-style encoder + caption encoder (contrastive), classification head and a
grid detection head for UI elements (labels come free from synthetic DOM renders)."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class VisionConfig:
    widths: tuple = (32, 64, 96, 128)
    embed_dim: int = 128
    text_buckets: int = 4096
    n_classes: int = 10
    n_ui: int = 7
    det_stride: int = 8

    def to_dict(self):
        d = asdict(self)
        d["widths"] = list(self.widths)
        return d

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d["widths"] = tuple(d["widths"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class Res(nn.Module):
    def __init__(self, cin, cout, stride):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = nn.BatchNorm2d(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = nn.BatchNorm2d(cout)
        self.skip = None if (cin == cout and stride == 1) else nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(y + (x if self.skip is None else self.skip(x)))


class Encoder(nn.Module):
    """Fully convolutional; returns (stride-8 feature map, pooled embedding)."""

    def __init__(self, cfg: VisionConfig):
        super().__init__()
        w = cfg.widths
        self.stem = nn.Sequential(nn.Conv2d(3, w[0], 3, 2, 1, bias=False), nn.BatchNorm2d(w[0]), nn.ReLU())  # /2
        self.l1 = Res(w[0], w[1], 2)  # /4
        self.l2 = Res(w[1], w[2], 2)  # /8  -> detection features
        self.l3 = Res(w[2], w[3], 2)  # /16
        self.proj = nn.Linear(w[3], cfg.embed_dim)
        self.fpn = nn.Conv2d(w[3], w[2], 1)

    def forward(self, x):
        f8 = self.l2(self.l1(self.stem(x)))
        f16 = self.l3(f8)
        pooled = self.proj(f16.mean(dim=(2, 3)))
        up = F.interpolate(self.fpn(f16), size=f8.shape[-2:], mode="nearest")
        return f8 + up, pooled


def text_ids(s: str, buckets: int) -> list[int]:
    words = re.findall(r"[a-z0-9]+", s.lower())
    feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return [int(hashlib.md5(w.encode()).hexdigest()[:8], 16) % buckets for w in feats] or [0]


class TextEncoder(nn.Module):
    def __init__(self, cfg: VisionConfig):
        super().__init__()
        self.buckets = cfg.text_buckets
        self.bag = nn.EmbeddingBag(cfg.text_buckets, cfg.embed_dim, mode="mean")
        self.mlp = nn.Sequential(nn.Linear(cfg.embed_dim, cfg.embed_dim), nn.GELU(), nn.Linear(cfg.embed_dim, cfg.embed_dim))

    def forward(self, captions: list[str]):
        ids, offs = [], []
        for c in captions:
            offs.append(len(ids))
            ids.extend(text_ids(c, self.buckets))
        dev = self.bag.weight.device
        e = self.bag(torch.tensor(ids, device=dev), torch.tensor(offs, device=dev))
        return self.mlp(e)


class XONVision(nn.Module):
    def __init__(self, cfg: VisionConfig):
        super().__init__()
        self.cfg = cfg
        self.enc = Encoder(cfg)
        self.txt = TextEncoder(cfg)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))
        self.cls = nn.Linear(cfg.embed_dim, cfg.n_classes)
        w = cfg.widths[2]
        self.det = nn.Sequential(nn.Conv2d(w, w, 3, 1, 1), nn.ReLU(), nn.Conv2d(w, cfg.n_ui + 1 + 4, 1))

    def embed_images(self, x):
        _, e = self.enc(x)
        return F.normalize(e, dim=-1)

    def embed_text(self, caps):
        return F.normalize(self.txt(caps), dim=-1)

    def contrastive_loss(self, x, caps):
        ie, te = self.embed_images(x), self.embed_text(caps)
        logits = ie @ te.t() * self.logit_scale.exp().clamp(max=100)
        y = torch.arange(len(caps), device=x.device)
        return (F.cross_entropy(logits, y) + F.cross_entropy(logits.t(), y)) / 2

    def classify(self, x):
        _, e = self.enc(x)
        return self.cls(e)

    def detect_raw(self, x):
        f, _ = self.enc(x)
        return self.det(f)  # (B, n_ui+1+4, H/8, W/8)

    def zero_shot(self, x, class_names: list[str], template: str = "a {}"):
        te = self.embed_text([template.format(c) for c in class_names])
        return self.embed_images(x) @ te.t()

    def n_params(self):
        return sum(p.numel() for p in self.parameters())
