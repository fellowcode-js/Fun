# XON project memory

Loaded by the XON agent at the start of every session (AGENTS.md is also accepted).

## What XON is
X-87 "X-Over-Node" (XON): a coding + design workstation. Crawler, trainer and agent nodes talk through plain files.

## Rules for agents working on this repo
- Never edit `evalsets/` (frozen), `xon/workstation/governor.py`, or safety filters (`xon/pipeline/clean_text.py`,
  `xon/pipeline/clean_images.py`, `xon/design/brand.py`) without explicit user approval (`--allow-protected`).
- Self-improvement changes go on a branch (`xon spawn`), and merge only when tests pass and the promotion gate shows
  no regression (`xon collect`).
- Run `python -m pytest -q -m "not slow"` before declaring work done.
- Never train on raw model output. Rejection-sampled outputs only after verification.

## Layout
- `xon/crawler` polite crawler, `xon/pipeline` cleaning + shards, `xon/datasets` open data + synthetic UI
- `xon/lm` code LM, `xon/vision` vision net, `xon/design` design tools, `xon/trainer` cycle + promotion
- `xon/agent` CLI, loop, tools, backends, manager; `xon/workstation` init/doctor/governor/dashboard

Related: [README.md](README.md) (usage), [PROGRESS.md](PROGRESS.md) (decisions behind these rules).
