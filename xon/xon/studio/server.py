"""XON Studio: a local app for the local model (chat, code, design, fix, agent), with an optional cloud bridge.

Binds 127.0.0.1 only. Every /api call needs the session token (printed at start, embedded in the launch URL).
Cloud keys given in the UI live in this process's memory only; they are never written to disk.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from xon import __version__, config

HERE = Path(__file__).parent
STATIC = HERE / "static"
SYSTEM = ("You are XON, a local coding and design assistant (Python, C++, HTML/CSS). Be concise. Put code in fenced "
          "blocks with a language tag. If you are not sure, say so.")


class State:
    def __init__(self, cfg: dict, token: str | None = None, coder=None):
        self.cfg = cfg
        self.root = Path(cfg["_root"])
        self.token = token or secrets.token_urlsafe(24)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(exist_ok=True)
        if not (self.workspace / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=self.workspace)
            subprocess.run(["git", "-c", "user.email=xon@localhost", "-c", "user.name=XON", "commit", "-q", "--allow-empty",
                            "-m", "XON Studio workspace"], cwd=self.workspace)
        self._coder = coder
        self._coder_err = None
        self.lock = threading.Lock()  # one local generation at a time (CPU)
        self.cloud: dict[str, dict] = {}  # provider -> {key, base, model}; memory only
        self.jobs: dict[str, dict] = {}
        self.errors: list[dict] = []

    # ---- models
    def coder(self):
        if self._coder is None and self._coder_err is None:
            try:
                from xon.lm.pretrained import load
                self._coder = load(self.cfg)
                if self._coder is None:
                    self._coder_err = "pretrained coder disabled or transformers missing"
            except Exception as e:  # pragma: no cover - depends on environment
                self._coder_err = f"{type(e).__name__}: {e}"
        return self._coder

    def cloud_backend(self, provider: str):
        c = self.cloud.get(provider, {})
        if provider == "anthropic":
            from xon.agent.backends.anthropic_compat import AnthropicBackend
            b = AnthropicBackend()
            b.key = c.get("key") or b.key
            b.base = (c.get("base") or b.base).rstrip("/")
            b.model = c.get("model") or b.model
            return b if b.key else None
        if provider == "openai":
            from xon.agent.backends.openai_compat import OpenAIBackend
            b = OpenAIBackend()
            b.key = c.get("key") or b.key
            b.base = (c.get("base") or b.base).rstrip("/")
            b.model = c.get("model") or b.model
            return b if (b.key or c.get("base")) else None
        return None

    def info(self) -> dict:
        from xon.lm import pretrained
        ck = config.path(self.cfg, "checkpoints") / "promoted"
        return {
            "version": __version__, "workspace": str(self.workspace),
            "models": {
                "local": {"name": self.cfg["lm"].get("pretrained", pretrained.DEFAULT), "available": pretrained.available()
                          and self.cfg["lm"].get("init") == "pretrained", "loaded": self._coder is not None, "error": self._coder_err,
                          "loading": self._coder is None and self._coder_err is None},
                "xon": {"name": "XON LM (trained by the cycle)", "available": (ck / "lm.pt").exists()},
                "anthropic": {"name": self.cloud_backend("anthropic").model if self.cloud_backend("anthropic") else "Claude",
                              "available": self.cloud_backend("anthropic") is not None},
                "openai": {"name": "OpenAI-compatible", "available": self.cloud_backend("openai") is not None},
            },
            "mcp": {"command": "xon mcp", "claude_code": f"claude mcp add xon -- {sys.executable} -m xon.agent.cli mcp --root {self.root}"},
            "errors": self.errors[-5:],
        }

    def note_error(self, where: str, e: BaseException) -> None:
        self.errors.append({"t": time.time(), "where": where, "error": f"{type(e).__name__}: {e}"})
        config.jsonl_append(config.path(self.cfg, "logs") / "studio_errors.jsonl", self.errors[-1])


def _sse(handler, obj: dict) -> None:
    handler.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
    handler.wfile.flush()


def make_handler(st: State):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        # ---- helpers
        def _send(self, code: int, ctype: str, body: bytes, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, "application/json", json.dumps(obj, default=str).encode())

        def _authed(self) -> bool:
            tok = self.headers.get("X-XON-Token") or parse_qs(urlsplit(self.path).query).get("token", [""])[0]
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
                return False  # block cross-site requests from other web pages
            return secrets.compare_digest(tok or "", st.token)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2_000_000:
                raise ValueError("request too large")
            return json.loads(self.rfile.read(n) or b"{}")

        # ---- GET
        def do_GET(self):
            path = urlsplit(self.path).path
            statics = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
                       "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
                       "/sw.js": ("sw.js", "text/javascript"), "/icon-192.png": ("icon-192.png", "image/png"),
                       "/icon-512.png": ("icon-512.png", "image/png"), "/biscuit.svg": ("biscuit.svg", "image/svg+xml")}
            if path in statics:
                f, ctype = statics[path]
                src = STATIC / f if (STATIC / f).exists() else config.find_root() / "xon/workstation/dashboard" / f
                return self._send(200, ctype, src.read_bytes())
            if not path.startswith("/api/"):
                return self._send(404, "text/plain", b"not found")
            if not self._authed():
                return self._json(401, {"error": "missing or wrong token; open the URL printed by `xon studio`"})
            if path == "/api/info":
                return self._json(200, st.info())
            if path.startswith("/api/agent/"):
                job = st.jobs.get(path.rsplit("/", 1)[1])
                if not job:
                    return self._json(404, {"error": "no such job"})
                return self._json(200, _job_view(job))
            if path == "/api/debug-bundle":
                from xon.studio.debug import bundle
                p = bundle(st.cfg, extra={"studio_errors": st.errors[-50:], "info": st.info()})
                return self._send(200, "application/zip", p.read_bytes(),
                                  {"Content-Disposition": f'attachment; filename="{p.name}"'})
            return self._json(404, {"error": "unknown endpoint"})

        # ---- POST
        def do_POST(self):
            path = urlsplit(self.path).path
            if not self._authed():
                return self._json(401, {"error": "missing or wrong token"})
            try:
                body = self._body()
                if path == "/api/chat":
                    return self._chat(body)
                if path == "/api/design":
                    return self._json(200, _design(st, body))
                if path == "/api/run":
                    return self._json(200, _run(st, body))
                if path == "/api/agent":
                    return self._json(200, _start_job(st, body))
                if path == "/api/cloud":
                    prov = body.get("provider")
                    if prov not in ("anthropic", "openai"):
                        return self._json(400, {"error": "provider must be anthropic or openai"})
                    st.cloud[prov] = {k: body.get(k, "") for k in ("key", "base", "model")}
                    return self._json(200, {"ok": True, "available": st.cloud_backend(prov) is not None})
                return self._json(404, {"error": "unknown endpoint"})
            except Exception as e:
                st.note_error(path, e)
                try:
                    return self._json(500, {"error": f"{type(e).__name__}: {e}"})
                except Exception:
                    return None

        def _chat(self, body: dict):
            model = body.get("model", "local")
            msgs = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant") and m.get("content")]
            if not msgs:
                return self._json(400, {"error": "no messages"})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            t0, n = time.time(), 0
            try:
                if model == "local":
                    coder = st.coder()
                    if coder is None:
                        _sse(self, {"error": st._coder_err or "local model unavailable"})
                        return
                    if not st.lock.acquire(timeout=1):
                        _sse(self, {"error": "local model is busy with another request"})
                        return
                    try:
                        for piece in coder.stream_chat([{"role": "system", "content": SYSTEM}] + msgs[-12:],
                                                       max_new=int(body.get("max_new", 768)), temperature=float(body.get("temperature", 0.3))):
                            n += 1
                            _sse(self, {"t": piece})
                    finally:
                        st.lock.release()
                elif model == "xon":
                    from xon.agent.tools import Context
                    m, tok = Context(st.root, st.cfg).lm()
                    if m is None:
                        _sse(self, {"error": "no promoted XON LM yet; run `xon train`"})
                        return
                    from xon.lm.generate import complete
                    _sse(self, {"t": complete(m, tok, msgs[-1]["content"], max_new=160, temperature=0.7)})
                elif model in ("anthropic", "openai"):
                    b = st.cloud_backend(model)
                    if b is None:
                        _sse(self, {"error": f"no {model} key configured: set it in Settings or the "
                                    f"{'ANTHROPIC_API_KEY' if model == 'anthropic' else 'OPENAI_API_KEY'} env var"})
                        return
                    r = b.chat([{"role": "system", "content": SYSTEM}] + msgs[-20:])
                    _sse(self, {"t": r["content"]})
                else:
                    _sse(self, {"error": f"unknown model {model}"})
                    return
                _sse(self, {"done": True, "seconds": round(time.time() - t0, 2), "pieces": n})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                st.note_error("chat", e)
                try:
                    _sse(self, {"error": f"{type(e).__name__}: {e}"})
                except Exception:
                    pass

    return H


def _design(st: State, body: dict) -> dict:
    from xon.design import critique, from_prompt
    prompt = body.get("prompt", "")
    try:
        g = from_prompt.generate(prompt)
    except from_prompt.Refused as e:
        return {"ok": False, "refused": True, "error": str(e)}
    try:
        rep = critique.critique_html(g["html"])
        rep.pop("image", None)
    except Exception as e:  # no browser: still return the page
        rep = {"score": None, "issues": [], "note": f"no headless browser for critique: {e}"}
    out = st.workspace / "design" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(g["html"])
    return {"ok": True, "engine": g["engine"], "html": g["html"], "score": rep.get("score"), "issues": rep.get("issues", [])[:12],
            "saved": str(out)}


def _run(st: State, body: dict) -> dict:
    from xon.agent.sandbox import run_cpp, run_python
    lang, code = body.get("lang", "python"), body.get("code", "")
    if lang in ("cpp", "c++"):
        return run_cpp(code, timeout=20)
    return run_python(code, timeout=20)


def _start_job(st: State, body: dict) -> dict:
    task = (body.get("task") or "").strip()
    if not task:
        raise ValueError("empty task")
    mode = body.get("mode", "auto-edit")
    if mode not in ("ask", "auto-edit", "full-auto"):
        raise ValueError("bad mode")
    jid = uuid.uuid4().hex[:10]
    log = config.path(st.cfg, "logs") / f"studio_job_{jid}.log"
    env = {**os.environ, "XON_CHECKPOINTS": str(config.path(st.cfg, "checkpoints")), "PYTHONUNBUFFERED": "1"}
    env.pop("XON_HOME", None)
    before = {p.name for p in (st.workspace / "artifacts").glob("*")} if (st.workspace / "artifacts").exists() else set()
    p = subprocess.Popen([sys.executable, "-m", "xon.agent.cli", "agent", task, "--mode", mode, "--yes", "--root", str(st.workspace),
                          "--workspace", body.get("folder", ".")], cwd=st.workspace, stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
    st.jobs[jid] = {"id": jid, "task": task, "proc": p, "log": log, "started": time.time(), "before": before, "ws": st.workspace}
    return {"ok": True, "id": jid}


def _job_view(job: dict) -> dict:
    p = job["proc"]
    arts = sorted(a for a in (job["ws"] / "artifacts").glob("*") if a.name not in job["before"]) if (job["ws"] / "artifacts").exists() else []
    art = arts[-1] if arts else None
    steps, summary, thoughts, plan = [], None, "", ""
    if art:
        if (art / "log.jsonl").exists():
            steps = [json.loads(l) for l in (art / "log.jsonl").read_text().splitlines() if l.strip()]
        if (art / "summary.json").exists():
            summary = json.loads((art / "summary.json").read_text())
        thoughts = (art / "thoughts.md").read_text() if (art / "thoughts.md").exists() else ""
        plan = (art / "plan.md").read_text() if (art / "plan.md").exists() else ""
    tail = job["log"].read_text()[-3000:] if job["log"].exists() else ""
    return {"id": job["id"], "task": job["task"], "running": p.poll() is None, "returncode": p.poll(),
            "seconds": round(time.time() - job["started"], 1), "plan": plan, "thoughts": thoughts, "summary": summary,
            "steps": [{"tool": s["tool"], "ok": s.get("ok"), "ms": s.get("ms"), "error": s.get("error"),
                       "what": (s.get("args") or {}).get("path") or (s.get("args") or {}).get("action") or (s.get("args") or {}).get("target") or ""}
                      for s in steps], "log_tail": tail if p.poll() not in (None, 0) else ""}


def serve(cfg: dict | None = None, port: int = 8790, token: str | None = None, open_browser: bool = False,
          background: bool = False, coder=None, preload: bool = True):
    cfg = cfg or config.load()
    st = State(cfg, token, coder=coder)
    if preload and coder is None:  # load the 1 GB model now so the first chat is not a 100 s cold start
        threading.Thread(target=st.coder, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(st))
    url = f"http://127.0.0.1:{srv.server_address[1]}/#token={st.token}"
    srv.studio_state = st  # type: ignore[attr-defined]
    srv.studio_url = url  # type: ignore[attr-defined]
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    print(f"XON Studio: {url}\n  (localhost only; the token in the URL is your key. Ctrl+C to quit.)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return srv
