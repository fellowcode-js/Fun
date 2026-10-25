# XON report

<!-- AUTO:START -->
_Generated 2026-10-25 05:23 UTC by `xon report` from logs, eval files and gate results._

### Hardware (probed)

| CPU | RAM | GPU | disk free | network | headless browser | tier |
|---|---|---|---|---|---|---|
| 4 | 15.7 GB | none | 28.5 GB | HTTP 200 | yes | A |

Budget plan: 0.5 h -> 0.79M params, 15.7M tokens (20.0 tok/param), measured 14995.4 tok/s.

### Honest expectations table (measured)

| tier | LM params | LM tokens seen | code pass@1 | code pass@5 | held-out ppl | bug-fix (blind) | design fidelity | UI detection F1@0.5 | recognition top-1 | zero-shot | wall-clock / cycle |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 0.79M | 11.5M | 0.000 | 0.000 | 18.80 | 0.733 | 0.926 | 0.401 | 0.978 | 0.828 | 16.4 min |

Tiers B and C were **not trained** (no GPU available). Their configs exist and are sized by the same code.

### Latest cycle detail

| metric | value | baseline / chance | note |
|---|---|---|---|
| code pass@1 / pass@5 (62 problems, 5 samples) | 0.000 / 0.000 | 0 | XON-written hidden tests |
| held-out perplexity (stdlib + HTML) | 18.80 | vocab  | bits/char 1.383 |
| bug-fix, dev set (20) | 1.000 | LM-only 0.000 | repair tool tuned on this set |
| bug-fix, **blind** set (15) | 0.733 | LM-only 0.000 | never used for tuning |
| screenshot->code fidelity (12 held-out) | 0.926 | bg-only 0.788, first layout 0.924 | SSIM+color+edge, 0..1 |
| UI detection P / R / F1 @IoU0.5 | 0.376 / 0.429 / 0.401 | – | per class: {'button': 0.412, 'input': 0.529, 'nav': 0.556, 'card': 0.385, 'modal': 0.889, 'table': 0.379, 'icon': 0.081} |
| recognition top-1 / top-5 / zero-shot | 0.978 / 1.000 / 0.828 | 0.100 | 10 procedural classes, 500 held-out |
| contrast checker accuracy | 1.000 | – | 10 WCAG reference pairs |
| critique: seeded-defect recall | 1.000 | – | generated page score 98 |

Example LM completion (first eval problem, greedy):

```python
def add_two(a, b):
    """Return a + b."""
    return self._ttinfo(a, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b, b

```

### Cycle history

| cycle | promoted | reason | new records | web images | pseudo-labeled | LM steps | LM min | vision steps | events |
|---|---|---|---|---|---|---|---|---|---|
| 1 | yes | no promoted checkpoint yet | 927 | 18 | 0 | 2799 | 9.54 | 887 | time_budget |

### Data

- Crawl rounds: 1 live, 1 mock. Live pages fetched: 30; mock pages fetched: 40.
- Stored records by kind: {'text': 30, 'code': 760, 'instruct': 119, 'image': 18}
- Rejects / quarantine / PII scrubs: {'reject:code_too_short': 37, 'reject:minified': 1, 'pii_EMAIL': 2, 'pii_SECRET': 2, 'quarantine:unsafe_adult': 1, 'reject:near_dup': 3, 'pii_PHONE': 1, 'pii_ADDRESS': 1, 'reject:image_dup': 2}
- Records by license: {'PSF-2.0': 476, 'BSD-3-Clause': 1, 'Apache-2.0': 1, 'CC-BY-SA': 70, 'W3C-doc': 20, 'ISC': 19, 'MIT': 189, 'CC-BY-4.0': 119, 'CC-BY': 32}

### Gates

| gate | pass | key numbers |
|---|---|---|
| M0 | not run | – |
| M1 | not run | – |
| M2 | not run | – |
| M3 | not run | – |
| M4 | not run | – |
<!-- AUTO:END -->
