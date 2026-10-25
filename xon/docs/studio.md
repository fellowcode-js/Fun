# XON Studio

<img src="biscuit.svg" alt="Biscuit" width="90" align="right">

A local app for XON's models, with Biscuit. It runs on your machine and lets you connect Claude (or any
OpenAI-compatible model) when you need more, and lets Claude Code drive XON to help you debug it.

## Start it
```bash
source .venv/bin/activate
xon studio --open          # prints http://127.0.0.1:8790/#token=...  and opens the browser
```
- The URL contains a random access token; every API call needs it. Studio listens on `127.0.0.1` only and
  rejects requests whose `Origin` is another website.
- The local model (Qwen2.5-Coder-0.5B, about 1 GB) loads in the background at startup, around 10 s with a warm
  disk cache and longer on first download. The sidebar dot turns green when it is ready.
- **Install as an app:** in Chrome or Edge, use "Install XON Studio" in the address bar (it is a PWA with a Biscuit
  icon). It then opens in its own window. The app shell works offline; the models still run locally.

## What's inside
| View | What it does |
|---|---|
| Chat | Streams answers from the chosen model. Code blocks get **Copy** and **Run** (Python/C++ run in XON's sandbox). **Ask Claude** sends the conversation to Claude. |
| Code | "Write, test, fix": XON's write -> test -> retry -> repair loop. Examples in your request (`f(2) == 4`, `'a' -> 'b'`) become fixed tests. Also "Find and fix the bug" for failing tests. |
| Design | Describe a page or app screen (dashboard, settings, desktop window, pricing...). Live preview in a sandboxed frame, critique score with computed contrast. |
| Agent | Any XON agent task; live plan, tool steps, thinking notes and summary. Runs in `workspace/` (a git repo with checkpoints). |
| Connect | Cloud model keys (memory only, never written to disk) and the MCP command for Claude Code. |
| Debug | Download a scrubbed debug bundle; current status. |

Models: **Local** (Qwen2.5-Coder-0.5B, Apache-2.0, CPU), **XON LM** (trained by XON's own cycle; small),
**Claude** (`ANTHROPIC_API_KEY` or a key typed in Connect), **OpenAI-compatible** (OpenAI, Ollama, vLLM, LM Studio:
set a base URL such as `http://localhost:11434/v1`).

## Connect Claude
There are three ways, depending on what you want.

1. **Claude answers inside Studio (cloud brain).** Put an Anthropic API key in Connect (or export
   `ANTHROPIC_API_KEY` before `xon studio`), then pick "Cloud: Claude" or press **Ask Claude**. With a key set, the
   `xon agent` command also plans with Claude instead of the rules planner.
2. **Claude Code drives XON (MCP).** On the machine where you run Claude Code:
   ```bash
   claude mcp add xon -- xon mcp --root /path/to/xon
   ```
   This repo also ships a project `.mcp.json`, so a Claude Code session opened on the repo offers to enable it.
   Claude then gets these tools:
   - `xon_status`, `xon_logs`, `xon_doctor`, `xon_evals`, `xon_debug_bundle`: read state and logs to debug XON.
   - `xon_chat`, `xon_complete`: use the local model.
   - `xon_agent`: run XON tasks.
   - `xon_design`, `xon_critique`, `xon_run`, `xon_lint`, `xon_test`: XON's design checks, sandbox and tests.
   - `xon_stop`, `xon_resume`: the kill switch.

   Claude Desktop config: `{"mcpServers": {"xon": {"command": "xon", "args": ["mcp", "--root", "/path/to/xon"]}}}`.
3. **Hand over a debug bundle.** `xon debug-bundle` (or Debug -> Download) writes one zip with config, log tails,
   cycle history, gate results, recent agent runs and the doctor report. Emails, phone numbers, API keys and
   key-like config values are scrubbed, and environment variables are listed by name only. Attach it in a Claude
   conversation.

## Remote use
Studio never listens on a public interface. To use it from another machine, tunnel:
`ssh -L 8790:127.0.0.1:8790 you@the-xon-box`, then open the printed URL locally.

## Limits
- The local model is small: fast for snippets and short functions, weak at multi-step reasoning. Use Claude for
  hard problems.
- Local generation runs one request at a time; a second request while one runs gets "local model is busy".
- Code written by the agent is verified only against tests (yours if you gave examples, otherwise model-written);
  the result says which.

Related: [README.md](../README.md) (overview), [cloud.md](cloud.md) (GPU setup), [REPORT.md](../REPORT.md) (measured numbers).
