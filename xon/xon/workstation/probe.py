"""Hardware / network / browser probe used by `xon init` and `xon doctor`."""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

CHROMIUM_CANDIDATES = [
    os.environ.get("XON_CHROMIUM", ""),
    "/opt/pw-browsers/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
]


def ram_gb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout
        return int(out) / 1024**3
    except Exception:
        return 0.0


def gpu_info() -> dict:
    info = {"cuda": False, "mps": False, "name": "", "vram_gb": 0.0, "count": 0}
    try:
        import torch
        if torch.cuda.is_available():
            info["cuda"] = True
            info["count"] = torch.cuda.device_count()
            p = torch.cuda.get_device_properties(0)
            info["name"], info["vram_gb"] = p.name, p.total_memory / 1024**3
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["mps"] = True
            info["name"] = "Apple MPS"
            info["count"] = 1
    except Exception as e:  # torch missing
        info["error"] = str(e)
    return info


def find_chromium() -> str | None:
    for c in CHROMIUM_CANDIDATES:
        if c and Path(c).exists():
            return c
    return shutil.which("chromium") or shutil.which("google-chrome")


def browser_ok() -> tuple[bool, str]:
    try:
        from xon.design.render import Renderer
        with Renderer() as r:
            r.screenshot_html("<p>ok</p>", width=64, height=32)
        return True, r.executable or "playwright-default"
    except Exception as e:
        return False, str(e).splitlines()[0][:200]


def network_ok(url: str = "https://pypi.org/simple/", timeout: float = 8.0) -> tuple[bool, float, str]:
    """Returns (ok, approx MB/s, detail). Small polite GET only."""
    try:
        import requests
        t = time.time()
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "XON-doctor/0.1"}, stream=True)
        n = 0
        for chunk in r.iter_content(65536):
            n += len(chunk)
            if n > 1_000_000:
                break
        dt = max(time.time() - t, 1e-3)
        return r.status_code < 500, n / dt / 1e6, f"HTTP {r.status_code}"
    except Exception as e:
        return False, 0.0, str(e).splitlines()[0][:160]


def probe(check_network: bool = True, check_browser: bool = True) -> dict:
    root = Path.cwd()
    du = shutil.disk_usage(root)
    out = {
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "ram_gb": round(ram_gb(), 1),
        "disk_free_gb": round(du.free / 1024**3, 1),
        "gpu": gpu_info(),
    }
    try:
        import torch
        out["torch"] = torch.__version__
    except Exception:
        out["torch"] = None
    if check_network:
        ok, mbps, detail = network_ok()
        out["network"] = {"ok": ok, "mb_per_s": round(mbps, 2), "detail": detail}
    if check_browser:
        ok, detail = browser_ok()
        out["browser"] = {"ok": ok, "detail": detail}
    return out


def pick_tier(p: dict) -> str:
    g = p.get("gpu", {})
    if g.get("cuda") and g.get("count", 0) >= 2 and g.get("vram_gb", 0) >= 20:
        return "C"
    if (g.get("cuda") and g.get("vram_gb", 0) >= 7) or (g.get("mps") and p.get("ram_gb", 0) >= 16):
        return "B"
    return "A"
