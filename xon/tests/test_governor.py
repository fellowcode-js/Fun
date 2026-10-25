import subprocess
import sys
import time

import pytest

from xon.workstation.governor import Governor, Halt


def test_stop_file_halts(home):
    g = Governor(home)
    g.tick()
    g.stop("test")
    with pytest.raises(Halt):
        g.tick()
    g.clear_stop()
    g.tick()


def test_request_and_bandwidth_caps(home):
    home["governor"]["max_requests_per_hour"] = 3
    home["governor"]["max_bandwidth_mb"] = 0.001
    g = Governor(home)
    g.reset_counters()
    assert [g.allow_request() for _ in range(4)] == [True, True, True, False]
    with pytest.raises(Halt):
        g.add_bytes(5000)


def test_disk_cap(home, tmp_path):
    from xon import config
    home["governor"]["max_disk_gb"] = 1e-6
    (config.path(home, "data") / "big.bin").write_bytes(b"x" * 5000)
    with pytest.raises(Halt):
        Governor(home).tick()


def test_gpu_hour_cap(home):
    home["governor"]["max_gpu_hours"] = 0.001
    g = Governor(home)
    g.reset_counters()
    with pytest.raises(Halt):
        g.add_gpu_seconds(10)


def test_stop_halts_running_node_within_seconds(home, tmp_path):
    """A crawler node in its idle loop exits within a few seconds of `xon stop`."""
    import os
    env = {**os.environ, "XON_HOME": str(tmp_path)}
    code = ("from xon import config; from xon.nodes.crawler_node import run_forever; "
            "cfg=config.load(); run_forever(cfg, interval_s=600, mock=True, open_data=False, max_pages=3)")
    p = subprocess.Popen([sys.executable, "-c", code], env=env, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    hb = tmp_path / "exchange" / "heartbeats" / "crawler.json"
    t0 = time.time()
    while time.time() - t0 < 60 and not (hb.exists() and "sleep" in hb.read_text()):
        time.sleep(0.2)
    assert hb.exists(), p.stdout.read().decode()[-2000:] if p.poll() is not None else "no heartbeat"
    t_stop = time.time()
    Governor(home).stop("test")
    p.wait(timeout=15)
    assert time.time() - t_stop < 5, "node took too long to honor STOP"
    assert "halted" in hb.read_text()
