"""`xon mcp`: an MCP server (stdio, JSON-RPC 2.0) so Claude Code / Claude Desktop can drive XON:
ask the local model, run XON's agent and tools, and read logs/status to debug the workstation.

Register with Claude Code:   claude mcp add xon -- xon mcp --root /path/to/xon
No third-party MCP SDK needed. Paths are jailed to the XON root; code runs in XON's sandbox.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

from xon import __version__, config

PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]


def _s(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


STR, INT, BOOL = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}

TOOLS = {
    "xon_status": ("Workstation status: governor caps/usage, node heartbeats, cycles (promoted or rolled back), promoted metrics.", _s({})),
    "xon_chat": ("Ask XON's local code model (Qwen2.5-Coder-0.5B on CPU) a question. Slow-ish (~12 tokens/s) and small: "
                 "good for quick code, weak at reasoning.", _s({"prompt": STR, "max_new": INT}, ["prompt"])),
    "xon_complete": ("Fill-in-the-middle code completion with the local model.", _s({"prefix": STR, "suffix": STR}, ["prefix"])),
    "xon_agent": ("Run an XON agent task in its workspace (build app, write_code, fix tests, design page). Blocks until done "
                  "(timeout_s, default 900). Returns the summary, plan, thoughts and tool log.",
                  _s({"task": STR, "mode": STR, "timeout_s": INT}, ["task"])),
    "xon_design": ("Generate an accessible HTML/CSS page or app screen from a description and critique it (computed contrast).",
                   _s({"prompt": STR}, ["prompt"])),
    "xon_critique": ("Critique an HTML file (path relative to the XON root): contrast, targets, labels, hierarchy, spacing.",
                     _s({"path": STR}, ["path"])),
    "xon_run": ("Run Python or C++ in XON's sandbox (temp dir, timeout, memory cap). lang: python|cpp.",
                _s({"lang": STR, "code": STR}, ["code"])),
    "xon_lint": ("Lint a Python or C++ file inside the XON root.", _s({"path": STR}, ["path"])),
    "xon_test": ("Run XON's own test suite (or a subset, e.g. tests/test_design.py). quick=true skips slow tests.",
                 _s({"target": STR, "quick": BOOL})),
    "xon_logs": ("Tail an XON log for debugging. name: a file in logs/ (e.g. lm_train.jsonl, crawler_node.log, "
                 "studio_errors.jsonl); omit to list logs.", _s({"name": STR, "lines": INT})),
    "xon_doctor": ("Run `xon doctor` (Python, torch, GPU, browser, disk, network, warm-start model) and return the report.", _s({})),
    "xon_evals": ("Latest measured numbers: last cycle metrics, warm-start coder eval, gate results.", _s({})),
    "xon_debug_bundle": ("Write a scrubbed debug zip (config, log tails, history, gates, artifacts, doctor) and return its path.", _s({})),
    "xon_stop": ("Kill switch: write the STOP file so every XON node halts within seconds.", _s({"reason": STR})),
    "xon_resume": ("Clear the STOP file.", _s({})),
}


class Server:
    def __init__(self, root: Path | None = None):
        self.cfg = config.load(Path(root) if root else None)
        self.root = Path(self.cfg["_root"])
        self._coder = None

    def coder(self):
        if self._coder is None:
            from xon.lm.pretrained import load
            self._coder = load(self.cfg)
            if self._coder is None:
                raise RuntimeError("local model unavailable (set [lm] init = \"pretrained\" and pip install transformers)")
        return self._coder

    # ---- tools
    def call(self, name: str, a: dict) -> str | dict:
        from xon.agent.sandbox import jail
        if name == "xon_status":
            from xon.workstation.dashboard.server import gather
            d = gather(self.cfg)
            return {"tier": d["tier"], "phase": d["status"].get("phase"), "governor": d["governor"], "nodes": d["nodes"],
                    "cycles": [{k: h[k] for k in ("cycle", "promoted", "reason")} for h in d["history"]], "promoted": d["promoted"]}
        if name == "xon_chat":
            sys_msg = {"role": "system", "content": "You are XON, a concise local coding assistant."}
            return self.coder().chat([sys_msg, {"role": "user", "content": a["prompt"]}], max_new=int(a.get("max_new", 512)))
        if name == "xon_complete":
            c = self.coder()
            return c.fill_in_middle(a["prefix"], a["suffix"]) if a.get("suffix") else c.generate(a["prefix"], max_new=96)[0]
        if name == "xon_agent":
            ws = self.root / "workspace"
            ws.mkdir(exist_ok=True)
            if not (ws / ".git").exists():
                subprocess.run(["git", "init", "-q"], cwd=ws)
                subprocess.run(["git", "-c", "user.email=xon@localhost", "-c", "user.name=XON", "commit", "-q", "--allow-empty", "-m", "init"], cwd=ws)
            mode = a.get("mode", "auto-edit")
            env = {**__import__("os").environ, "XON_CHECKPOINTS": str(config.path(self.cfg, "checkpoints"))}
            env.pop("XON_HOME", None)
            p = subprocess.run([sys.executable, "-m", "xon.agent.cli", "agent", a["task"], "--mode", mode, "--yes", "--root", str(ws)],
                               cwd=ws, capture_output=True, text=True, timeout=int(a.get("timeout_s", 900)), env=env)
            arts = sorted((ws / "artifacts").glob("*"))
            art = arts[-1] if arts else None
            out = {"returncode": p.returncode, "stdout_tail": p.stdout[-4000:], "stderr_tail": p.stderr[-2000:] if p.returncode else ""}
            if art:
                for f in ("plan.md", "thoughts.md"):
                    if (art / f).exists():
                        out[f] = (art / f).read_text()[-3000:]
                if (art / "summary.json").exists():
                    out["summary"] = json.loads((art / "summary.json").read_text())
                out["artifacts"] = str(art)
            return out
        if name == "xon_design":
            from xon.studio.server import State, _design
            r = _design(State(self.cfg), a)
            r["html"] = (r.get("html") or "")[:20000]
            return r
        if name == "xon_critique":
            from xon.design.critique import critique_file
            rep = critique_file(jail(self.root, a["path"]))
            rep.pop("image", None)
            return rep
        if name == "xon_run":
            from xon.agent.sandbox import run_cpp, run_python
            return run_cpp(a["code"], timeout=20) if a.get("lang") in ("cpp", "c++") else run_python(a["code"], timeout=20)
        if name == "xon_lint":
            from xon.agent.tools import Context, registry
            return registry()["lint"].run(Context(self.root, self.cfg), jail(self.root, a["path"]).relative_to(self.root).as_posix())
        if name == "xon_test":
            cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
            if a.get("quick", True):
                cmd += ["-m", "not slow"]
            target = a.get("target") or "tests"
            jail(self.root, target)
            p = subprocess.run(cmd + [target], cwd=self.root, capture_output=True, text=True, timeout=1800)
            return {"ok": p.returncode == 0, "output_tail": (p.stdout + p.stderr)[-5000:]}
        if name == "xon_logs":
            logs = config.path(self.cfg, "logs")
            if not a.get("name"):
                return sorted(f.name for f in logs.glob("*") if f.is_file())
            f = jail(logs, a["name"])
            return "\n".join(f.read_text(errors="replace").splitlines()[-int(a.get("lines", 80)):])
        if name == "xon_doctor":
            from xon.workstation import doctor
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor.run(check_network=False)
            return buf.getvalue()
        if name == "xon_evals":
            ck, ex = config.path(self.cfg, "checkpoints"), config.path(self.cfg, "exchange")
            hist = [json.loads(l) for l in (ck / "history.jsonl").read_text().splitlines()] if (ck / "history.jsonl").exists() else []
            rd = lambda p: json.loads(p.read_text()) if p.exists() else None  # noqa: E731
            return {"last_cycle": {k: hist[-1][k] for k in ("cycle", "promoted", "reason", "metrics")} if hist else None,
                    "warm_start_coder": rd(ck / "pretrained_eval.json"), "gates": rd(ex / "gates.json")}
        if name == "xon_debug_bundle":
            from xon.studio.debug import bundle
            return {"path": str(bundle(self.cfg))}
        if name == "xon_stop":
            from xon.workstation.governor import Governor
            Governor(self.cfg).stop(a.get("reason", "stopped via MCP"))
            return "STOP written; nodes halt within seconds"
        if name == "xon_resume":
            from xon.workstation.governor import Governor
            Governor(self.cfg).clear_stop()
            return "STOP cleared"
        raise KeyError(f"unknown tool {name}")

    # ---- JSON-RPC
    def handle(self, msg: dict) -> dict | None:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:  # notification (e.g. notifications/initialized)
            return None
        try:
            if method == "initialize":
                want = params.get("protocolVersion", PROTOCOLS[0])
                result = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "xon", "version": __version__},
                          "instructions": "XON is a local coding + design workstation. Use xon_status / xon_logs / xon_doctor "
                                          "to debug it, xon_chat for the local model, xon_agent to run tasks."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s) in TOOLS.items()]}
            elif method == "tools/call":
                name, args = params.get("name"), params.get("arguments") or {}
                if name not in TOOLS:
                    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
                try:
                    out = self.call(name, args)
                    text = out if isinstance(out, str) else json.dumps(out, indent=1, default=str)
                    result = {"content": [{"type": "text", "text": text[:100_000]}], "isError": False}
                except Exception as e:
                    result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"}], "isError": True}
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}

    def serve_stdio(self) -> None:
        out = sys.stdout
        sys.stdout = sys.stderr  # anything printed by tools must not corrupt the JSON-RPC stream
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                out.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
                out.flush()
                continue
            resp = self.handle(msg)
            if resp is not None:
                out.write(json.dumps(resp) + "\n")
                out.flush()


def main(root: str | None = None) -> None:
    Server(Path(root) if root else None).serve_stdio()
