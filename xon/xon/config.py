"""Config, paths and logging shared by every XON node."""
from __future__ import annotations

import copy
import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

DEFAULTS: dict = {
    "xon": {"tier": "A", "seed": 1337},
    "paths": {
        "data": "data",
        "checkpoints": "checkpoints",
        "evalsets": "evalsets",
        "artifacts": "artifacts",
        "exchange": "exchange",  # shared folder between nodes
        "logs": "logs",
    },
    "budget": {"wall_hours": 0.5, "gpu_price_per_hour": 0.0, "max_dollars": 0.0},
    "governor": {
        "max_disk_gb": 5.0,
        "max_bandwidth_mb": 500.0,
        "max_requests_per_hour": 600,
        "max_gpu_hours": 0.0,
        "min_free_disk_gb": 2.0,
    },
    "crawler": {
        "user_agent": "XON-crawler/0.1 (+https://github.com/fellowcode-js/fun; contact: xon-crawler@example.org)",
        "default_delay_s": 2.0,
        "max_pages": 40,
        "timeout_s": 15,
        "max_bytes": 2_000_000,
        "live": False,
    },
    "lm": {"config": "tiny", "init": "pretrained", "pretrained": "Qwen/Qwen2.5-Coder-0.5B-Instruct", "minutes": 8},
    "vision": {"config": "tiny", "minutes": 4},
    "agent": {
        "backend": "auto",  # auto | rules | local | openai | anthropic
        "permission_mode": "ask",  # ask | auto-edit | full-auto
        "max_steps": 40,
        "shell_timeout_s": 120,
        "tool_allowlist": [],
        "hooks": {"pre_tool": [], "post_tool": []},
    },
    "transport": {"kind": "folder", "url": ""},
    "promote": {"noise_margin": 0.002, "max_regression": 0.02},
    "distill": {"enabled": False},
    "practice": {"limit": 10},  # verified practice solutions per cycle (rejection sampling); 0 disables
}


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("XON_HOME")
    if env:
        return Path(env).resolve()
    p = (start or Path.cwd()).resolve()
    for q in [p, *p.parents]:
        if (q / "xon.toml").exists() or (q / "XON.md").exists() and (q / "xon").is_dir():
            return q
    # fall back to the source checkout that holds this package
    return Path(__file__).resolve().parent.parent


def deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(root: Path | None = None) -> dict:
    root = root or find_root()
    cfg = copy.deepcopy(DEFAULTS)
    f = root / "xon.toml"
    if f.exists():
        with open(f, "rb") as fh:
            cfg = deep_merge(cfg, tomllib.load(fh))
    cfg["_root"] = str(root)
    return cfg


def path(cfg: dict, key: str) -> Path:
    env = os.environ.get(f"XON_{key.upper()}")
    p = Path(env) if env else Path(cfg["paths"][key])
    if not p.is_absolute():
        p = Path(cfg["_root"]) / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(type(v))


def dump_toml(cfg: dict) -> str:
    """Minimal TOML writer (tables of scalars/lists, one nesting level of sub-tables)."""
    lines: list[str] = []

    def table(name: str, d: dict):
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        subs = {k: v for k, v in d.items() if isinstance(v, dict)}
        lines.append(f"[{name}]")
        for k, v in scalars.items():
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
        for k, v in subs.items():
            table(f"{name}.{k}", v)

    for k, v in cfg.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        table(k, v)
    return "\n".join(lines)


def save(cfg: dict, root: Path | None = None) -> Path:
    root = root or Path(cfg.get("_root") or find_root())
    f = root / "xon.toml"
    f.write_text("# XON config (written by `xon init`; edit freely)\n" + dump_toml(cfg))
    return f


_LOGGERS: dict[str, logging.Logger] = {}


def log(name: str = "XON") -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    lg = logging.getLogger(name)
    if not lg.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(f"%(asctime)s XON[{name}] %(levelname)s %(message)s", "%H:%M:%S"))
        lg.addHandler(h)
        lg.setLevel(os.environ.get("XON_LOG", "INFO"))
    _LOGGERS[name] = lg
    return lg


def jsonl_append(p: Path, rec: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": round(time.time(), 3), **rec}
    with open(p, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def jsonl_read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out
