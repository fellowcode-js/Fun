import copy
import math

import numpy as np
import torch
import torch.nn as nn

from xon.exhort import ExhortConfig, diagnose, exhort, find_groups, heal, lm_batches, lm_loss


def mse(m, b):
    return ((m(b[0]) - b[1]) ** 2).mean()


def trained_mlp(seed=0):
    torch.manual_seed(seed)
    X = torch.randn(640, 4)
    Y = torch.sin(X[:, :1] * 2) + X[:, 1:2] * X[:, 2:3]
    m = nn.Sequential(nn.Linear(4, 32), nn.ReLU(), nn.Linear(32, 1))
    opt = torch.optim.Adam(m.parameters(), 1e-2)
    for _ in range(200):
        loss = mse(m, (X[:512], Y[:512]))
        opt.zero_grad()
        loss.backward()
        opt.step()
    tr = [(X[i:i + 128], Y[i:i + 128]) for i in range(0, 512, 128)]
    return m, tr, [(X[512:], Y[512:])]


def test_finds_groups_in_lm_and_mlp():
    from xon.lm.model import LMConfig, XONLM
    lm = XONLM(LMConfig(vocab_size=64, d_model=32, n_layers=2, n_heads=2, n_kv_heads=1, seq_len=32))
    assert [g.name for g in find_groups(lm)] == ["blocks.0.ffn", "blocks.1.ffn"]
    m = nn.Sequential(nn.Linear(3, 8), nn.ReLU(), nn.Linear(8, 2))
    assert len(find_groups(m)) == 1 and find_groups(m)[0].size == 8


def test_diagnose_flags_dead_and_broken():
    m, tr, _ = trained_mlp()
    with torch.no_grad():
        m[0].bias[:5] = -50  # never fires
        m[0].weight[7, 1] = float("nan")
    rep = diagnose(m, tr, mse, ExhortConfig(max_frac=0.5, useless_q=0))[0]
    assert rep.broken == [7]
    assert set(range(5)) <= set(rep.dead)


def test_healthy_network_untouched():
    m, tr, va = trained_mlp()
    before = copy.deepcopy(m.state_dict())
    r = exhort(m, tr, va, mse, ExhortConfig(dead_rel=0.0, useless_q=0))
    assert r["found"] == 0 and not r["kept"]
    assert all(torch.equal(before[k], v) for k, v in m.state_dict().items())


def test_birth_preserves_output_then_heals_better_than_baseline():
    m, tr, va = trained_mlp(1)
    with torch.no_grad():
        m[0].bias[:10] = -50
    base = copy.deepcopy(m)
    heal(base, tr, mse, 150, 5e-3)
    r = exhort(m, tr, va, mse, ExhortConfig(max_frac=0.4, useless_q=0, heal_steps=150, heal_lr=5e-3))
    assert r["kept"] and r["reborn"] >= 10
    assert r["val_at_birth"] <= r["val_before"] + 0.01  # the first step after birth never hurts (here it helps)
    assert r["val_after"] < float(mse(base, va[0]).detach())  # and ends up better than just training on


def test_broken_lm_is_repaired():
    from xon.lm.model import LMConfig, XONLM
    torch.manual_seed(0)
    lm = XONLM(LMConfig(vocab_size=64, d_model=32, n_layers=2, n_heads=2, n_kv_heads=1, seq_len=32))
    ids = np.array([i % 17 for i in range(4000)])
    with torch.no_grad():
        lm.blocks[1].ffn.w2.weight[0, 3] = float("inf")
    r = exhort(lm, lm_batches(ids, 32, 30), lm_batches(ids, 32, 3, seed=5), lm_loss, ExhortConfig(heal_steps=20, heal_lr=3e-3))
    assert r["broken"] >= 1 and r["kept"] and math.isfinite(r["val_after"])
    assert all(torch.isfinite(p).all() for p in lm.parameters())


def test_rollback_when_worse():
    m, tr, va = trained_mlp(2)
    with torch.no_grad():
        m[0].bias[:6] = -50
    before = copy.deepcopy(m.state_dict())
    # a huge learning rate wrecks the heal step -> Exhort must undo everything
    r = exhort(m, tr, va, mse, ExhortConfig(max_frac=0.4, useless_q=0, heal_steps=30, heal_lr=5.0))
    assert not r["kept"] and "rolled back" in r["reason"]
    assert all(torch.equal(before[k], v) for k, v in m.state_dict().items())
