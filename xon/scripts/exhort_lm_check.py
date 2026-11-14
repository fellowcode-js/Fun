"""Fair check on the promoted XON LM: Exhort vs the same number of extra training steps without rebirth.
Run after `xon train`: python scripts/exhort_lm_check.py"""
import copy

from xon import config
from xon.exhort import ExhortConfig, _mean_loss, exhort, heal, lm_batches, lm_loss
from xon.lm import data as lmdata
from xon.lm.train import load_model
from xon.tokenizer import BPETokenizer
from xon.trainer.replay import Replay

cfg = config.load()
ck = config.path(cfg, "checkpoints")
tr_ids, va_ids = lmdata.tokenize(Replay(ck / "replay.json").items, BPETokenizer.load(ck / "promoted" / "tokenizer.json"), seed=1)
for seed in (1, 2, 3):
    base = load_model(ck / "promoted" / "lm.pt").train()
    tr = lm_batches(tr_ids, 128, 60, seed=seed)
    va = lm_batches(va_ids, 128, 6, seed=99)
    a = copy.deepcopy(base)
    heal(a, tr, lm_loss, 60, 1e-3)
    b = copy.deepcopy(base)
    r = exhort(b, tr, va, lm_loss, ExhortConfig(seed=seed))
    print(f"seed {seed}: start {_mean_loss(base, va, lm_loss):.4f} | 60 extra steps only {_mean_loss(a, va, lm_loss):.4f} | "
          f"Exhort ({r['reborn']} reborn) {r['val_after']:.4f}")
