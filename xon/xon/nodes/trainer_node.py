"""Trainer node: pull shards, train, evaluate on frozen sets, promote checkpoints. Repeats."""
from __future__ import annotations

import time

from xon import config
from xon.nodes.common import heartbeat
from xon.trainer.cycle import Cycle
from xon.workstation.governor import Governor, Halt

log = config.log("trainer-node")


def run(cfg: dict, cycles: int = 1, wait_for_data_s: float = 600, quick: bool = False, **kw) -> list[dict]:
    gov = Governor(cfg, "trainer")
    out = []
    shard_root = config.path(cfg, "exchange") / "shards" / "manifest.json"
    try:
        t0 = time.time()
        while not shard_root.exists() and time.time() - t0 < wait_for_data_s:
            gov.tick()
            heartbeat(cfg, "trainer", phase="waiting_for_shards")
            time.sleep(1)
        for i in range(cycles):
            gov.tick()
            heartbeat(cfg, "trainer", phase="cycle", cycle=i + 1)
            out.append(Cycle(cfg, quick=quick).run(**kw))
            heartbeat(cfg, "trainer", phase="idle", last_cycle=out[-1]["cycle"], promoted=out[-1]["promoted"])
    except Halt as e:
        heartbeat(cfg, "trainer", phase="halted", reason=str(e))
        log.warning(f"halted: {e}")
    return out
