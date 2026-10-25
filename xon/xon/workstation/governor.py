"""Governor: hard caps on disk, bandwidth, requests/hour, GPU hours + STOP-file kill switch.

Every node calls `gov.tick()` in its main loop; `gov.tick()` raises `Halt` within one loop
iteration of a STOP file appearing or a cap being hit. State is a JSON file so caps hold
across processes and restarts.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from pathlib import Path

from xon import config


class Halt(RuntimeError):
    """Raised when the kill switch is set or a hard cap is exceeded."""


def dir_size_gb(p: Path) -> float:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1024**3


class Governor:
    def __init__(self, cfg: dict | None = None, node: str = "node"):
        self.cfg = cfg or config.load()
        self.root = Path(self.cfg["_root"])
        self.caps = self.cfg["governor"]
        self.node = node
        self.stop_file = self.root / "STOP"
        self.state_file = config.path(self.cfg, "exchange") / "governor.json"
        self._lock = threading.Lock()
        self._last_disk_check = 0.0
        self._disk_gb = 0.0

    # ---- persistent counters
    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"bytes": 0, "requests": [], "gpu_seconds": 0.0}

    def _save(self, s: dict) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(s))
        os.replace(tmp, self.state_file)

    # ---- kill switch
    def stop(self, reason: str = "user") -> None:
        self.stop_file.write_text(json.dumps({"reason": reason, "t": time.time()}))

    def clear_stop(self) -> None:
        self.stop_file.unlink(missing_ok=True)

    def stopped(self) -> bool:
        return self.stop_file.exists()

    # ---- checks
    def disk_gb(self, force: bool = False) -> float:
        if force or time.time() - self._last_disk_check > 10:
            self._disk_gb = sum(dir_size_gb(config.path(self.cfg, k)) for k in ("data", "checkpoints"))
            self._last_disk_check = time.time()
        return self._disk_gb

    def tick(self) -> None:
        if self.stopped():
            raise Halt(f"STOP file present ({self.stop_file})")
        if self.disk_gb() > self.caps["max_disk_gb"]:
            raise Halt(f"disk cap {self.caps['max_disk_gb']} GB exceeded ({self._disk_gb:.2f} GB)")
        free = shutil.disk_usage(self.root).free / 1024**3
        if free < self.caps.get("min_free_disk_gb", 0):
            raise Halt(f"free disk {free:.1f} GB below floor {self.caps['min_free_disk_gb']} GB")

    def disk_pressure(self) -> float:
        """0..1+ fraction of the disk cap in use (used by the pruning policy)."""
        return self.disk_gb(force=True) / max(self.caps["max_disk_gb"], 1e-9)

    def allow_request(self) -> bool:
        with self._lock:
            s = self._load()
            now = time.time()
            s["requests"] = [t for t in s["requests"] if now - t < 3600]
            if len(s["requests"]) >= self.caps["max_requests_per_hour"]:
                self._save(s)
                return False
            if s["bytes"] / 1e6 >= self.caps["max_bandwidth_mb"]:
                return False
            s["requests"].append(now)
            self._save(s)
            return True

    def add_bytes(self, n: int) -> None:
        with self._lock:
            s = self._load()
            s["bytes"] = s.get("bytes", 0) + int(n)
            self._save(s)
            if s["bytes"] / 1e6 > self.caps["max_bandwidth_mb"]:
                raise Halt(f"bandwidth cap {self.caps['max_bandwidth_mb']} MB exceeded")

    def add_gpu_seconds(self, sec: float) -> None:
        if self.caps.get("max_gpu_hours", 0) <= 0:
            return
        with self._lock:
            s = self._load()
            s["gpu_seconds"] = s.get("gpu_seconds", 0.0) + sec
            self._save(s)
            if s["gpu_seconds"] / 3600 > self.caps["max_gpu_hours"]:
                raise Halt(f"GPU-hour cap {self.caps['max_gpu_hours']} exceeded")

    def usage(self) -> dict:
        s = self._load()
        now = time.time()
        return {
            "stopped": self.stopped(),
            "disk_gb": round(self.disk_gb(force=True), 3),
            "max_disk_gb": self.caps["max_disk_gb"],
            "bandwidth_mb": round(s.get("bytes", 0) / 1e6, 2),
            "max_bandwidth_mb": self.caps["max_bandwidth_mb"],
            "requests_last_hour": len([t for t in s.get("requests", []) if now - t < 3600]),
            "max_requests_per_hour": self.caps["max_requests_per_hour"],
            "gpu_hours": round(s.get("gpu_seconds", 0) / 3600, 3),
        }

    def reset_counters(self) -> None:
        self._save({"bytes": 0, "requests": [], "gpu_seconds": 0.0})
