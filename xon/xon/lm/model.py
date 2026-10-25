"""XON code LM: decoder-only transformer (RMSNorm, RoPE, GQA, SwiGLU, KV-cache)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class LMConfig:
    vocab_size: int = 4096
    d_model: int = 256
    n_layers: int = 4
    n_heads: int = 8
    n_kv_heads: int = 2
    ffn_mult: float = 2.667
    seq_len: int = 256
    dropout: float = 0.0
    rope_base: float = 10000.0
    tie_embeddings: bool = True
    grad_checkpoint: bool = False
    n_image_tokens: int = 0  # >0 enables the vision->LM bridge prefix (Tier B+)
    image_dim: int = 0

    @property
    def head_dim(self) -> int:
        return self.d_model // self.n_heads

    @property
    def ffn_dim(self) -> int:
        h = int(self.d_model * self.ffn_mult)
        return (h + 31) // 32 * 32

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LMConfig":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})

    def n_params(self, include_embedding: bool = True) -> int:
        d, f, L = self.d_model, self.ffn_dim, self.n_layers
        kv = self.n_kv_heads * self.head_dim
        per = d * d + 2 * d * kv + d * d + 3 * d * f + 2 * d
        emb = self.vocab_size * d * (1 if self.tie_embeddings else 2)
        return L * per + d + (emb if include_embedding else 0)


def shape_for_params(n_target: int, vocab: int, seq_len: int) -> LMConfig:
    """Pick a sensible (d_model, layers, heads) whose parameter count is closest to n_target."""
    best, best_err = None, float("inf")
    for d in (64, 96, 128, 192, 256, 320, 384, 512, 640, 768, 1024, 1280, 1536, 2048):
        heads = max(2, d // 64) if d >= 128 else max(2, d // 32)
        kv = max(1, heads // 4)
        for L in range(2, 33):
            if L > 4 * max(1, d // 64) + 4:  # keep aspect ratio sane
                break
            c = LMConfig(vocab_size=vocab, d_model=d, n_layers=L, n_heads=heads, n_kv_heads=kv, seq_len=seq_len)
            err = abs(math.log(c.n_params() / max(n_target, 1)))
            if err < best_err:
                best, best_err = c, err
    assert best is not None
    return best


class RMSNorm(nn.Module):
    def __init__(self, d: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(d))

    def forward(self, x):
        return x * torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps).type_as(x) * self.weight


def rope_tables(head_dim: int, max_len: int, base: float, device=None):
    inv = 1.0 / (base ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    t = torch.arange(max_len, device=device).float()
    freqs = torch.outer(t, inv)
    return freqs.cos(), freqs.sin()


def apply_rope(x, cos, sin):
    # x: (B, H, T, D); cos/sin: (T, D/2)
    x1, x2 = x[..., 0::2], x[..., 1::2]
    c, s = cos[None, None], sin[None, None]
    out = torch.stack((x1 * c - x2 * s, x1 * s + x2 * c), dim=-1)
    return out.flatten(-2)


class Attention(nn.Module):
    def __init__(self, cfg: LMConfig):
        super().__init__()
        self.cfg = cfg
        hd = cfg.head_dim
        self.wq = nn.Linear(cfg.d_model, cfg.n_heads * hd, bias=False)
        self.wk = nn.Linear(cfg.d_model, cfg.n_kv_heads * hd, bias=False)
        self.wv = nn.Linear(cfg.d_model, cfg.n_kv_heads * hd, bias=False)
        self.wo = nn.Linear(cfg.n_heads * hd, cfg.d_model, bias=False)

    def forward(self, x, cos, sin, cache=None):
        B, T, _ = x.shape
        c = self.cfg
        q = self.wq(x).view(B, T, c.n_heads, c.head_dim).transpose(1, 2)
        k = self.wk(x).view(B, T, c.n_kv_heads, c.head_dim).transpose(1, 2)
        v = self.wv(x).view(B, T, c.n_kv_heads, c.head_dim).transpose(1, 2)
        q, k = apply_rope(q, cos, sin), apply_rope(k, cos, sin)
        if cache is not None:
            if "k" in cache:
                k = torch.cat([cache["k"], k], dim=2)
                v = torch.cat([cache["v"], v], dim=2)
            cache["k"], cache["v"] = k, v
        rep = c.n_heads // c.n_kv_heads
        if rep > 1:
            k = k.repeat_interleave(rep, dim=1)
            v = v.repeat_interleave(rep, dim=1)
        causal = cache is None or T > 1
        if cache is not None and T > 1 and k.shape[2] != T:
            # prefill on top of an existing cache: build explicit mask
            S = k.shape[2]
            mask = torch.ones(T, S, dtype=torch.bool, device=x.device).tril(S - T)
            y = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        else:
            y = F.scaled_dot_product_attention(q, k, v, is_causal=causal,
                                               dropout_p=c.dropout if self.training else 0.0)
        return self.wo(y.transpose(1, 2).reshape(B, T, -1))


class SwiGLU(nn.Module):
    def __init__(self, cfg: LMConfig):
        super().__init__()
        self.w1 = nn.Linear(cfg.d_model, cfg.ffn_dim, bias=False)
        self.w3 = nn.Linear(cfg.d_model, cfg.ffn_dim, bias=False)
        self.w2 = nn.Linear(cfg.ffn_dim, cfg.d_model, bias=False)

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class Block(nn.Module):
    def __init__(self, cfg: LMConfig):
        super().__init__()
        self.n1, self.n2 = RMSNorm(cfg.d_model), RMSNorm(cfg.d_model)
        self.attn, self.ffn = Attention(cfg), SwiGLU(cfg)

    def forward(self, x, cos, sin, cache=None):
        x = x + self.attn(self.n1(x), cos, sin, cache)
        return x + self.ffn(self.n2(x))


class XONLM(nn.Module):
    def __init__(self, cfg: LMConfig):
        super().__init__()
        self.cfg = cfg
        self.emb = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layers))
        self.norm = RMSNorm(cfg.d_model)
        self.head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        if cfg.tie_embeddings:
            self.head.weight = self.emb.weight
        # vision->LM bridge: projects image-encoder features into prefix tokens
        self.bridge = None
        if cfg.n_image_tokens > 0 and cfg.image_dim > 0:
            self.bridge = nn.Sequential(nn.Linear(cfg.image_dim, cfg.d_model * cfg.n_image_tokens), nn.Tanh())
        cos, sin = rope_tables(cfg.head_dim, cfg.seq_len * 4 + cfg.n_image_tokens + 8, cfg.rope_base)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)
        self.apply(self._init)
        for n, p in self.named_parameters():
            if n.endswith("wo.weight") or n.endswith("w2.weight"):
                nn.init.normal_(p, std=0.02 / math.sqrt(2 * cfg.n_layers))

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, std=0.02)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, idx, targets=None, caches=None, pos: int = 0, image_feats=None, loss_mask=None):
        x = self.emb(idx)
        n_img = 0
        if image_feats is not None and self.bridge is not None:
            pre = self.bridge(image_feats).view(idx.shape[0], self.cfg.n_image_tokens, self.cfg.d_model)
            x = torch.cat([pre, x], dim=1)
            n_img = pre.shape[1]
        T = x.shape[1]
        cos, sin = self.cos[pos:pos + T], self.sin[pos:pos + T]
        for i, b in enumerate(self.blocks):
            cache = caches[i] if caches is not None else None
            if self.cfg.grad_checkpoint and self.training and cache is None:
                x = torch.utils.checkpoint.checkpoint(b, x, cos, sin, None, use_reentrant=False)
            else:
                x = b(x, cos, sin, cache)
        logits = self.head(self.norm(x))
        if n_img:
            logits = logits[:, n_img:]
        if targets is None:
            return logits, None
        l = F.cross_entropy(logits.reshape(-1, logits.size(-1)).float(), targets.reshape(-1), reduction="none")
        if loss_mask is not None:
            m = loss_mask.reshape(-1).float()
            loss = (l * m).sum() / m.sum().clamp(min=1)
        else:
            mask = (targets.reshape(-1) >= 0).float()
            loss = (l * mask).sum() / mask.sum().clamp(min=1)
        return logits, loss

    def new_caches(self):
        return [dict() for _ in self.blocks]

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())
