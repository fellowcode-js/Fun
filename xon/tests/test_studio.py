import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class FakeCoder:
    name = "fake"
    license = "test"

    def stream_chat(self, messages, max_new=100, temperature=0.3):
        for w in ["Hello ", "from ", "the ", "local ", "model."]:
            yield w


@pytest.fixture
def studio(home):
    from xon.studio.server import serve
    srv = serve(home, port=0, token="tok", background=True, coder=FakeCoder(), preload=False)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, srv.studio_state
    srv.shutdown()


def req(url, body=None, token="tok", origin=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["X-XON-Token"] = token
    if origin:
        h["Origin"] = origin
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h,
                               method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def sse(raw: bytes) -> list[dict]:
    return [json.loads(l[6:]) for l in raw.decode().split("\n\n") if l.startswith("data: ")]


def test_auth_and_origin(studio):
    base, _ = studio
    assert req(base + "/")[0] == 200 and b"XON Studio" in req(base + "/")[1]
    assert req(base + "/api/info", token=None)[0] == 401
    assert req(base + "/api/info", token="wrong")[0] == 401
    assert req(base + "/api/info", origin="https://evil.example")[0] == 401
    code, body = req(base + "/api/info", origin="http://127.0.0.1:1234")
    info = json.loads(body)
    assert code == 200 and "local" in info["models"] and "claude mcp add xon" in info["mcp"]["claude_code"]


def test_streaming_chat_local(studio):
    base, _ = studio
    code, raw = req(base + "/api/chat", {"model": "local", "messages": [{"role": "user", "content": "hi"}]})
    ev = sse(raw)
    assert code == 200 and "".join(e.get("t", "") for e in ev) == "Hello from the local model." and ev[-1]["done"]


def test_cloud_bridge_with_fake_openai_server(studio):
    base, st = studio
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            out = json.dumps({"choices": [{"message": {"role": "assistant", "content": "cloud says hi"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    fake = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    try:
        code, raw = req(base + "/api/chat", {"model": "openai", "messages": [{"role": "user", "content": "hi"}]})
        assert "no openai key" in sse(raw)[0]["error"]
        assert json.loads(req(base + "/api/cloud", {"provider": "openai", "key": "sk-test", "base": f"http://127.0.0.1:{fake.server_address[1]}/v1"})[1])["available"]
        code, raw = req(base + "/api/chat", {"model": "openai", "messages": [{"role": "user", "content": "hi"}]})
        assert sse(raw)[0]["t"] == "cloud says hi" and seen[0]["messages"][-1]["content"] == "hi"
        assert not any("sk-test" in p.read_text(errors="ignore") for p in Path(st.root).rglob("*") if p.is_file() and p.suffix in (".toml", ".json", ".jsonl"))
    finally:
        fake.shutdown()


def test_sandbox_run_and_agent_job(studio):
    base, _ = studio
    r = json.loads(req(base + "/api/run", {"lang": "python", "code": "print(2 + 2)"})[1])
    assert r["ok"] and r["stdout"].strip() == "4"
    jid = json.loads(req(base + "/api/agent", {"task": "make an accessible palette from #e0b000", "mode": "auto-edit"})[1])["id"]
    t0 = time.time()
    while time.time() - t0 < 120:
        j = json.loads(req(base + f"/api/agent/{jid}")[1])
        if not j["running"]:
            break
        time.sleep(0.5)
    assert not j["running"] and j["returncode"] == 0 and j["steps"][0]["tool"] == "design" and j["summary"]


def test_debug_bundle_is_scrubbed(studio, tmp_path):
    base, st = studio
    (Path(st.root) / "xon.toml").write_text('[agent]\napi_key = "sk-SHOULDNOTLEAK1234567890"\n')
    logs = Path(st.root) / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "x.log").write_text("contact me at jane@example.com token=ghp_" + "a" * 36 + "\n")
    code, raw = req(base + "/api/debug-bundle")
    assert code == 200
    p = tmp_path / "b.zip"
    p.write_bytes(raw)
    with zipfile.ZipFile(p) as z:
        allt = "".join(z.read(n).decode(errors="ignore") for n in z.namelist())
        assert "doctor.txt" in z.namelist() and "environment.json" in z.namelist()
    assert "SHOULDNOTLEAK" not in allt and "jane@example.com" not in allt and "ghp_aaaa" not in allt


def test_mcp_stdio_protocol(home, tmp_path):
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                                           "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "xon_run", "arguments": {"lang": "python", "code": "print(7*6)"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "xon_logs", "arguments": {"name": "../../etc/passwd"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "xon_stop", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "bogus"}]
    p = subprocess.run([sys.executable, "-m", "xon.agent.cli", "mcp", "--root", str(Path(home["_root"]))],
                       input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=120)
    out = {d["id"]: d for d in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
    assert out[1]["result"]["serverInfo"]["name"] == "xon" and out[1]["result"]["protocolVersion"] == "2025-06-18"
    names = {t["name"] for t in out[2]["result"]["tools"]}
    assert {"xon_chat", "xon_agent", "xon_status", "xon_logs", "xon_debug_bundle"} <= names
    assert '"stdout": "42\\n"' in out[3]["result"]["content"][0]["text"]
    assert out[4]["result"]["isError"] and "escapes" in out[4]["result"]["content"][0]["text"]
    assert (Path(home["_root"]) / "STOP").exists()
    assert out[6]["error"]["code"] == -32601
    assert len(out) == 6  # the notification got no reply
