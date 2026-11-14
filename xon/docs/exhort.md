# Exhort

Exhort finds neurons that are **broken**, **dead** or **useless**, deletes them and reincarnates them, then keeps
the change only if the network did not get worse. Code: `xon/exhort.py`. Tests: `tests/test_exhort.py`.

## What counts as a bad neuron
A neuron is one hidden unit of a feed-forward block: in the XON LM, one SwiGLU unit (row of `w1`/`w3`, column of
`w2`); in an MLP or conv head, one output row/channel of the first layer and the matching input of the next.
Exhort finds these blocks by itself (`find_groups`), so it also works on the vision net's detector head or any
`Sequential(Linear, act, Linear)` you hand it.

| Kind | Test (on a calibration batch) |
|---|---|
| broken | NaN or inf in its weights, or a non-finite activation |
| dead | mean \|activation\| below 2% of the layer's median: it never fires |
| useless | it fires but its effect (activation x outgoing weight size) is in the bottom 2% of the layer |

At most 10% of a layer is reincarnated per run (`max_frac`); broken neurons are always fixed.

## How the rebirth works
1. **Delete** every bad neuron in the whole network first (so one broken layer cannot poison the others).
2. **Try 4 random rebirths** per neuron, scaled like the healthy neurons of that layer. Keep the one whose output
   the loss gradient wants most (the newborn that can help the most).
3. **Start gently:** the outgoing weights start at zero (the network's output is unchanged), then take one small
   step down the gradient so the neuron is useful from the first moment.
4. **Heal** with a short training burst (60 steps), then compare validation loss with the loss before Exhort.
   Worse -> everything is rolled back.

## Use it
```bash
xon exhort --dry-run        # diagnose the promoted XON LM only
xon exhort                  # reincarnate + heal; result in checkpoints/exhort/lm.pt
xon exhort --apply          # also replace the promoted LM (old one kept as promoted/lm.pre-exhort.pt)
```
It also runs automatically after every LM training run in the cycle (`[exhort] enabled = true` in `xon.toml`);
the promotion gate still decides whether the result is promoted. In Studio: the **Exhort** view. For Claude Code:
the `xon_exhort` MCP tool. From Python:
```python
from xon.exhort import exhort, ExhortConfig
report = exhort(model, train_batches, val_batches, loss_fn, ExhortConfig())   # loss_fn(model, batch) -> loss
```

## Measured (honest)
- **Sabotaged nets** (`scripts/exhort_bench.py`, 5 seeds, 10 of 32 neurons killed): validation MSE after the same
  150 training steps: just training on **0.149**, random rebirth 0.123, Exhort **0.113** (24% lower than training on).
- **Broken LM** (one inf weight, so the loss is NaN and the model is unusable): Exhort finds it, rebuilds it, loss
  becomes finite again (test `test_broken_lm_is_repaired`).
- **Healthy trained XON LM** (`scripts/exhort_lm_check.py`, 3 seeds): it had no dead or broken neurons, only the 24
  weakest. Exhort 5.529 / 5.543 / 5.577 vs the same 60 extra training steps without rebirth 5.530 / 5.543 / 5.577.
  So on a healthy network the gain comes from the extra training, not from the rebirth. Exhort earns its keep when
  neurons really die (ReLU nets, high learning rates, NaN accidents), which is exactly when you want it.

Related: [studio.md](studio.md) (the Exhort view), [subagents.md](subagents.md).
