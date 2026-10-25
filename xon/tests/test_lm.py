import numpy as np
import torch

from xon.lm import data as lmdata
from xon.lm.model import LMConfig, XONLM
from xon.lm.train import train


def tiny_cfg(v=300):
    return LMConfig(vocab_size=v, d_model=64, n_layers=2, n_heads=2, n_kv_heads=1, seq_len=32)


def test_kv_cache_matches_full_forward():
    torch.manual_seed(0)
    m = XONLM(tiny_cfg()).eval()
    x = torch.randint(0, 300, (1, 24))
    full, _ = m(x)
    caches = m.new_caches()
    outs = [m(x[:, :10], caches=caches)[0]]
    for t in range(10, 24):
        outs.append(m(x[:, t:t + 1], caches=caches, pos=t)[0])
    assert torch.allclose(torch.cat(outs, 1), full, atol=1e-4)


def test_gqa_and_param_count():
    c = tiny_cfg()
    assert c.n_params() == XONLM(c).n_params()


def test_fim_document_format():
    import random
    d = lmdata.fim("def f(x):\n    return x + 1\n", random.Random(0))
    assert d.startswith("<|fim_prefix|>") and "<|fim_suffix|>" in d and "<|fim_middle|>" in d


def _ids(n=6000):
    rng = np.random.default_rng(0)
    pat = np.tile(np.arange(20), n // 20)  # learnable periodic sequence
    noise = rng.integers(0, 300, n)
    return np.where(rng.random(n) < 0.05, noise, pat).astype(np.int32)


def test_loss_falls(tmp_path):
    ids = _ids()
    r = train(tiny_cfg(), ids, ids[:1000], tmp_path, max_steps=80, batch=8, lr=3e-3, warmup=5, eval_every=40)
    log = [l for l in (tmp_path / "train_log.jsonl").read_text().splitlines() if '"loss"' in l]
    import json
    first, last = json.loads(log[0])["loss"], json.loads(log[-1])["loss"]
    assert last < first * 0.6, (first, last)
    assert r["val_loss"] < 3.0


def test_oom_recovery_halves_batch(tmp_path):
    ids = _ids()
    r = train(tiny_cfg(), ids, ids[:1000], tmp_path, max_steps=30, batch=8, inject={"oom_at": 5})
    ev = [e for e in r["events"] if e["event"] == "oom_recovered"]
    assert ev and ev[0]["batch"] == 4 and ev[0]["grad_checkpoint"] is True
    assert r["step"] == 30


def test_nan_rollback_lowers_lr(tmp_path):
    ids = _ids()
    r = train(tiny_cfg(), ids, ids[:1000], tmp_path, max_steps=40, batch=8, lr=3e-3, eval_every=10, inject={"nan_at": 25})
    ev = [e for e in r["events"] if e["event"] == "nan_rollback"]
    assert ev and ev[0]["to_step"] == 20 and abs(ev[0]["new_lr"] - 1.5e-3) < 1e-9
    assert np.isfinite(r["val_loss"])


def test_preemption_checkpoint_and_resume(tmp_path):
    ids = _ids()
    r1 = train(tiny_cfg(), ids, ids[:1000], tmp_path, max_steps=60, batch=8, inject={"sigterm_at": 15})
    assert r1["preempted"] and r1["step"] == 15
    r2 = train(tiny_cfg(), ids, ids[:1000], tmp_path, max_steps=60, batch=8)
    assert any(e["event"] == "resumed" and e["step"] == 15 for e in r2["events"])
    assert r2["step"] == 60


def test_pass_at_k_estimator():
    from xon.lm.eval import pass_at_k
    assert pass_at_k(5, 0, 1) == 0.0
    assert pass_at_k(5, 5, 1) == 1.0
    assert abs(pass_at_k(5, 1, 1) - 0.2) < 1e-9
    assert pass_at_k(5, 1, 5) == 1.0
