"""`xon doctor`: check the workstation and print exact fixes instead of stack traces."""
from __future__ import annotations

import importlib
import shutil
import sys

from xon.workstation import probe

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


def run(check_network: bool = True) -> int:
    rows: list[tuple[str, str, str, str]] = []

    def add(status, name, detail, fix=""):
        rows.append((status, name, detail, fix))

    v = sys.version_info
    add(OK if v >= (3, 10) else FAIL, "python", sys.version.split()[0],
        "" if v >= (3, 10) else "install Python 3.10+ (e.g. `uv python install 3.12`)")
    for mod, pipname in [("torch", "torch"), ("numpy", "numpy"), ("yaml", "pyyaml"), ("PIL", "pillow"),
                         ("requests", "requests"), ("playwright", "playwright")]:
        try:
            m = importlib.import_module(mod)
            add(OK, mod, getattr(m, "__version__", "installed"))
        except Exception:
            fix = (f"pip install {pipname}" if mod != "torch"
                   else "pip install torch --index-url https://download.pytorch.org/whl/cpu  (or the CUDA wheel)")
            add(FAIL, mod, "missing", fix)
    g = probe.gpu_info()
    if g.get("cuda"):
        add(OK, "gpu", f"CUDA {g['name']} x{g['count']} {g['vram_gb']:.1f} GB")
    elif g.get("mps"):
        add(OK, "gpu", "Apple MPS")
    else:
        hint = "nvidia-smi found but torch has no CUDA: reinstall the CUDA torch wheel" if shutil.which("nvidia-smi") else \
            "no GPU: Tier A (CPU) will be used. For Tier B see docs/cloud.md"
        add(WARN, "gpu", "none", hint)
    p = probe.probe(check_network=check_network, check_browser=True)
    add(OK if p["ram_gb"] >= 4 else WARN, "ram", f"{p['ram_gb']} GB", "" if p["ram_gb"] >= 4 else "close other apps; Tier A needs ~4 GB")
    add(OK if p["disk_free_gb"] >= 5 else WARN, "disk", f"{p['disk_free_gb']} GB free",
        "" if p["disk_free_gb"] >= 5 else "free >=5 GB or lower governor.max_disk_gb in xon.toml")
    b = p["browser"]
    add(OK if b["ok"] else WARN, "browser", b["detail"],
        "" if b["ok"] else "pip install playwright && playwright install chromium  (or set XON_CHROMIUM=/path/to/chrome); "
                           "design tools fall back to DOM-only checks without it")
    if check_network:
        n = p["network"]
        add(OK if n["ok"] else WARN, "network", f"{n['detail']} ~{n['mb_per_s']} MB/s",
            "" if n["ok"] else "offline: XON will use the mock web server (`xon crawl --mock`); set HTTPS_PROXY if behind a proxy")
    width = max(len(r[1]) for r in rows)
    for st, name, detail, fix in rows:
        print(f"[{st}] {name.ljust(width)}  {detail}")
        if fix:
            print(f"       fix: {fix}")
    fails = sum(1 for r in rows if r[0] == FAIL)
    print(f"\nXON doctor: {len(rows) - fails}/{len(rows)} checks passed or warned, {fails} failed.")
    return 1 if fails else 0
