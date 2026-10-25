# XON — X-87 "X-Over-Node"

A self-building workstation for **coding and designing**. One command builds the workstation, pulls code, design
material and image-text pairs from the web and open datasets (politely, with license checks), cleans and stores
them, trains a small code LM and a vision net, evaluates them on frozen sets, promotes only real improvements, and
repeats. An agent CLI (`xon`) drives it all, writes code, designs UIs, screenshots and critiques them, and fixes bugs
— including bugs in XON's own pipeline, on a branch, merged only when tests pass.

**Honest scope:** XON will not match big commercial models. At Tier A (CPU) the code LM is under a million parameters
and its pass@k on unseen problems is ~0. What works well at Tier A is measured in `REPORT.md`: the design tools
(computed contrast, critique, palettes, screenshot→HTML reconstruction), UI-element detection, recognition, search-based
bug repair, the polite crawler/cleaning pipeline, and the full self-training loop with promotion gating.

## Documents
- [REPORT.md](REPORT.md): what XON measurably does, every number from an eval, gate results, live vs mock, limits.
- [PROGRESS.md](PROGRESS.md): build log (done, decisions, incidents, next); read first when resuming work.
- [XON.md](XON.md): project memory the agent loads every session; rules for agents editing this repo.
- [docs/cloud.md](docs/cloud.md): copy-paste steps for a rented GPU box (Tier B/C), Docker, split nodes, spot.
- [data/samples/README.md](data/samples/README.md): the tiny license-clean samples that ship in the zip.

## Quick start
```bash
unzip xon.zip && cd xon
./scripts/setup.sh && source .venv/bin/activate
xon doctor                 # checks Python, torch, GPU, Chromium, disk, network; prints exact fixes
xon init                   # probes hardware, picks tier A/B/C, sizes the run (try --budget 8h or '$40' --gpu-price 1.2)
xon start --all            # crawler + trainer + agent supervisor + dashboard (http://127.0.0.1:8787)
```
`xon stop` (or the dashboard's STOP button) halts every node within seconds.

## The agent
```bash
xon agent "build a todo app called Errands with a teal theme" --mode auto-edit --workspace errands
xon agent "fix the failing tests in tests/test_pipeline.py"
xon agent "design a dark landing page with three feature cards and a newsletter form"
xon design critique --path page.html          # computed WCAG contrast, targets, labels, hierarchy, spacing
xon design from_screenshot --path shot.png --out recon.html
xon design palette --base '#e0b000'           # accessible palette, every pair verified
xon spawn "task"; xon agents; xon collect      # parallel agents in git worktrees
xon repl                                       # /plan /run /review /test /diff /undo /agents /spawn /crawl /train /design /status
```
Permission modes: `ask` (default), `auto-edit`, `full-auto`. Project-dir jail, destructive-command denylist, no secret
reads, every tool call logged to `artifacts/<task-id>/`. Eval sets, governor and safety filters are protected.

Brain: an external chat endpoint is used for planning when `ANTHROPIC_API_KEY` or `XON_OPENAI_KEY`/`OPENAI_API_KEY`
(+`XON_OPENAI_BASE` for any OpenAI-compatible server) is set; otherwise a deterministic **rules planner** handles the
core task shapes (build app, fix tests, design/critique page) and says so for anything else. The local XON LM does
completion (`xon complete`) and ranks repair candidates.

## Nodes
Crawler, trainer and agent talk only through files in a shared exchange (folder, rsync or S3-compatible bucket):
`xon start --node crawler` on one box, `xon start --node trainer` on another. See `docs/cloud.md`.

## Milestone gates
`xon gate m0` … `m4` run automated checks (M0: fresh Tier A end-to-end < 30 min; M4: agent builds + designs an app
and fixes a seeded bug in XON's pipeline). Results land in `REPORT.md` via `xon report`.

## Layout
`xon/workstation` (init, doctor, governor, budget, dashboard) · `xon/nodes` · `xon/crawler` · `xon/datasets` ·
`xon/pipeline` · `xon/tokenizer` · `xon/lm` · `xon/vision` · `xon/design` · `xon/trainer` · `xon/agent` ·
`evalsets/` (frozen) · `tests/` · `scripts/` · `docs/`.

## Legal and safety
robots.txt + crawl-delay, honest user agent with contact, per-domain limits, allowlist/denylist, no forms or logins,
license captured per item (no-train and all-rights-reserved skipped), PII and secrets scrubbed, unsafe content
quarantined, design tools refuse to reproduce named brands' logos or trade dress. No scraped data ships in the zip.

Related: [REPORT.md](REPORT.md) (measured results), [PROGRESS.md](PROGRESS.md) (build log), [docs/cloud.md](docs/cloud.md) (GPU setup).
