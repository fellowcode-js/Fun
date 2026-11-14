"""`xon debug-bundle`: one zip with what someone (or Claude) needs to debug XON, with secrets scrubbed.

Contains config, log tails, cycle history, gate results, node heartbeats, recent agent artifacts, doctor output and
package versions. Environment variables are listed by NAME only. Every text file passes the PII/secret scrubber.
"""
from __future__ import annotations

import io
import json
import platform
import re
import sys
import time
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from xon import __version__, config
from xon.pipeline.clean_text import scrub_pii

KEYISH = re.compile(r"(?i)(key|token|secret|password|passwd|auth)")


def _scrub(text: str) -> str:
    text, _ = scrub_pii(text)
    # also blank values of key-like assignments in config/env-style text
    return re.sub(r'(?im)^(\s*[\w.-]*(?:key|token|secret|password)[\w.-]*\s*[=:]\s*).+$', r"\1<REDACTED>", text)


def _tail(p: Path, n: int = 400) -> str:
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def bundle(cfg: dict | None = None, out: Path | None = None, extra: dict | None = None) -> Path:
    cfg = cfg or config.load()
    root = Path(cfg["_root"])
    logs, ck, ex = config.path(cfg, "logs"), config.path(cfg, "checkpoints"), config.path(cfg, "exchange")
    out = Path(out) if out else root / f"xon-debug-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    files: dict[str, str] = {}
    if (root / "xon.toml").exists():
        files["xon.toml"] = (root / "xon.toml").read_text()
    for p in sorted(logs.glob("*"))[-40:]:
        if p.is_file() and p.suffix in (".log", ".jsonl", ".time"):
            files[f"logs/{p.name}"] = _tail(p)
    for name in ("history.jsonl", "cycle_state.json", "promoted/metrics.json", "pretrained_eval.json"):
        if (ck / name).exists():
            files[f"checkpoints/{name}"] = _tail(ck / name, 2000)
    for name in ("status.json", "gates.json", "governor.json", "crawl_stats.jsonl"):
        if (ex / name).exists():
            files[f"exchange/{name}"] = _tail(ex / name, 400)
    for p in (ex / "heartbeats").glob("*.json") if (ex / "heartbeats").exists() else []:
        files[f"exchange/heartbeats/{p.name}"] = p.read_text()
    for arts in (root / "artifacts", root / "workspace" / "artifacts"):
        for a in sorted(arts.glob("*"))[-5:] if arts.exists() else []:
            for f in ("plan.md", "summary.json", "log.jsonl", "thoughts.md", "status.json"):
                if (a / f).exists():
                    files[f"artifacts/{a.name}/{f}"] = _tail(a / f)
    buf = io.StringIO()
    try:
        from xon.workstation import doctor
        with redirect_stdout(buf):
            doctor.run(check_network=False)
    except Exception as e:
        buf.write(f"doctor failed: {e}")
    files["doctor.txt"] = buf.getvalue()
    pkgs = {}
    for mod in ("torch", "numpy", "transformers", "playwright", "PIL", "requests", "yaml"):
        try:
            pkgs[mod] = getattr(__import__(mod), "__version__", "installed")
        except Exception:
            pkgs[mod] = "missing"
    import os
    files["environment.json"] = json.dumps({
        "xon": __version__, "python": sys.version, "platform": platform.platform(), "packages": pkgs,
        "env_var_names": sorted(k for k in os.environ if k.startswith(("XON_", "ANTHROPIC", "OPENAI", "CUDA", "HF_"))),
        "note": "values of environment variables are never included",
    }, indent=1)
    if extra:
        files["studio.json"] = json.dumps(extra, indent=1, default=str)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, _scrub(text))
        z.writestr("README.txt", "XON debug bundle. Secrets, emails, phone numbers and key-like config values are scrubbed.\n"
                                 "Share it with whoever is helping you debug (e.g. attach it in a Claude conversation).\n")
    return out
