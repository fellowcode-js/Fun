# XON progress log

Re-read this first when resuming. Newest entries at the bottom of each section.

## Environment (probed 2026-10-25)
- Ran inside a Claude Code **cloud container** (not the user's own machine): 4 CPU, 15.7 GB RAM, no GPU, ~28 GB disk.
- Python 3.13, torch 2.x CPU wheel, Playwright with system Chromium at /opt/pw-browsers/chromium.
- Network: live (PyPI, Hugging Face datasets-server, docs.python.org, MDN, w3.org, raw.githubusercontent.com reachable).
- No LLM API key present, so the agent's planner runs on the deterministic rules backend.
- Tier selected: **A** (CPU).

## Done
- Scaffold, config (xon.toml), logging, paths.
- Tokenizer (byte-level BPE, FIM/file/tool specials, HTML/CSS atomic tokens).
- LM: RMSNorm, RoPE, GQA, SwiGLU, KV-cache (verified equal to full forward), FIM, training loop with
  cosine/warmup, grad accumulation, clipping, AMP on CUDA, time + SIGTERM checkpoints, resume, OOM + NaN recovery.
- Budget sizing (20 tokens/param, measured 100-step benchmark), hardware tiers, `xon init`, `xon doctor`.
- Governor (disk/bandwidth/requests/GPU-hour caps, STOP file).
- Renderer + synthetic UI generator (HTML/CSS -> screenshot + DOM labels).
- Crawler: robots.txt (incl. fractional crawl-delay), allowlist/denylist, rate limits, 429/403 backoff + demotion,
  resume, license + no-train detection; mock web (polite site, 429 site, 403 site).
- Pipeline: PII/secret scrub, unsafe-content quarantine, quality filters, MinHash near-dedupe, image phash dedupe,
  shards + manifest, eval-set contamination guard, cold-shard pruning.
- Open datasets: Python stdlib (local, PSF), codeparrot/github-code-clean (per-row permissive filter), MBPP (CC-BY-4.0).
- Frozen eval sets: 62 code problems, 20 bug-fix (+15 blind), 10 WCAG contrast cases, held-out UI/recognition/ppl.
- Vision net (ResNet encoder + caption encoder + classification + UI grid detection), evals.
- Design tools: from_prompt, from_screenshot (render-compare loop), critique (computed contrast), palette/type, tokens.
- Trainer cycle, replay buffer, promotion gate, registry.
- Nodes (crawler/trainer/agent) + transport (folder/rsync/S3).
- Agent: tools, sandbox, permissions, hooks, memory, artifacts, rules planner, OpenAI/Anthropic backends, fault
  localization (Ochiai) + search-based repair, manager (worktrees), CLI, dashboard.
- Tests: 50+ passing (fast suite).

## Decisions
- Eval sets written by XON (CC0) so they ship license-clean; MBPP only used for *training* instruction pairs.
- Repair tool was developed while looking at evalsets/bugfix.jsonl; `bugfix_blind.jsonl` was written afterwards and
  never used for tuning. Report the blind number as the honest one.
- Rules planner is labeled as such everywhere; LLM planning needs an API key.

## Known issues / fixed
- FIXED: robots.txt fetch recursed through crawl-delay lookup and re-requested robots.txt (49 requests to
  docs.python.org at 2 s spacing during the first live crawl). Regression test added.
- FIXED: stdlib robotparser ignores fractional Crawl-delay; XON parses it itself.

## Results so far
- Cycle 1 (16.4 min): promoted. ppl 18.8, pass@k 0, blind bug-fix 11/15, fidelity 0.926 (bg-only 0.788),
  UI F1 0.40, recognition 0.978, zero-shot 0.83.
- Cycle 2: ROLLED BACK by the gate (ppl regressed 72%: fixed step budget on 34 new records overfit). Vision had
  improved (UI F1 0.53) but was discarded with it.
  -> Fix: LM and vision now promoted independently; LM increments capped at 3 epochs, full replay, 0.3x LR.
  -> Open-dataset pulls resume from a saved offset (new rows each round).
- Gates: M0 PASS (fresh home, 16.7 min), M1 PASS, M2 PASS (stability smoke only, no GPU), M3 PASS, M4 PASS.
- M4 found a test gap: the agent's first patch (`<= 40`) passed tests; added a boundary test, now it restores `< 40`.

- Cycle 3 (via `xon start --all`): LM and vision both promoted (ppl 15.9, UI F1 0.555, zero-shot 0.956).
- Kill switch under load: trainer halted 0.19 s, supervisor 0.61 s after STOP.
- Clean-folder unzip -> setup.sh -> init -> start --all: 19.6 min, works.
- Full suite 57/57 (incl. slow). Vault lint of docs: 0 orphans.

## v0.2 (user asked: smarter, more Python + C++, better UI/GUI design, better thinking, more tools, a cat mascot)
- Warm start: Qwen2.5-Coder-0.5B-Instruct (Apache-2.0) as the local coder. Python pass@1 0.784 / pass@5 0.887,
  C++ pass@1 0.75 / pass@5 0.857 on XON's frozen sets (from 0 with the from-scratch LM).
- C++: frozen 28-problem eval (g++ compiled hidden tests), blind 8-bug C++ set, sandbox C++ runner, C++ repair.
- Repair: mutation search then LLM rewrite (reason first, 4 samples, verified). Python blind 11/15 -> 13/15; C++ 8/8.
- Data: C++/C in the HF code pull (permissive rows only), nlohmann/json + fmt seeds; cppreference skipped (Cloudflare
  challenge, robots 403 = disallowed). Python/C++ up-weighted 2x. Practice round: 22/60 verified solutions kept.
- GUI: synthetic v2 (app/sidebar, settings, desktop windows, pricing) with 6 new detector classes; GUI prompts in
  from_prompt; critique found my own contrast/target/spacing bugs in the GUI CSS, fixed (all 5 sample prompts 100).
- Thinking: write_code loop (generate, test, note, retry with sampling; tests frozen after attempt 1; task examples
  become asserts; no-assert tests refused), best-of-two design + critique rounds, LLM routing for unknown tasks.
  Fixed a false positive found in testing: the model had rewritten its own tests to pass.
- Tools: python_run, cpp_build (+ASan/UBSan), lint, sqlite, serve, patch, think, docs_search, codegen (23 total).
- Mascot: Biscuit, a brown-and-white cat (dashboard header + speech bubble, favicon, README, REPL banner).
- Cycle 4: LM promoted (ppl 15.9 -> 13.9); vision rolled back (new head undertrained: v2 F1 0.17). Cycle 5 = vision
  focused (900 GUI pages, 20 min).

## Next (if continued)
- Tier B on a real GPU (docs/cloud.md); OCR for from_screenshot text; better icon detection.

Related: [REPORT.md](REPORT.md) (measured results this log leads to), [XON.md](XON.md) (rules decided along the way).
