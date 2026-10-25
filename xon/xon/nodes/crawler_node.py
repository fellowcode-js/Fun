"""Crawler node: fetch + clean web data (live or mock) and open datasets, write shards + manifest to the exchange."""
from __future__ import annotations

import time
from pathlib import Path

from xon import config
from xon.crawler.spider import Spider
from xon.nodes.common import heartbeat
from xon.nodes.transport import make_transport
from xon.pipeline.process import process_raw
from xon.workstation.governor import Governor, Halt

log = config.log("crawler-node")


def crawl_once(cfg: dict, mock: bool | None = None, max_pages: int | None = None, open_data: bool = True,
               online_open: bool | None = None, gov: Governor | None = None) -> dict:
    gov = gov or Governor(cfg, "crawler")
    live = cfg["crawler"].get("live", False) if mock is None else not mock
    raw = config.path(cfg, "data") / ("raw_live" if live else "raw_mock")
    local_shards = config.path(cfg, "data") / "crawl_shards"
    stats: dict = {"live": live}
    heartbeat(cfg, "crawler", phase="crawl", live=live)
    if live:
        sp = Spider(cfg, out_dir=raw, gov=gov)
        stats["crawl"] = sp.run(max_pages=max_pages or cfg["crawler"]["max_pages"])
    else:
        from xon.crawler.mockweb import MockWeb, mock_allowlist
        with MockWeb() as m:
            sp = Spider(cfg, out_dir=raw, gov=gov, allow=mock_allowlist(), seeds=m.seeds(), delay_override=0.02,
                        state_path=raw / f"state-{int(time.time())}.json")
            stats["crawl"] = sp.run(max_pages=max_pages or 120)
    heartbeat(cfg, "crawler", phase="clean")
    stats["clean"] = process_raw(raw, local_shards, config.path(cfg, "evalsets"))
    if open_data:
        from xon.datasets import fetch_open
        flag = config.path(cfg, "data") / "open_fetched.flag"
        if not flag.exists():
            stats["open"] = fetch_open.run(cfg, local_shards, online=(live if online_open is None else online_open), gov=gov)
            flag.write_text(str(time.time()))
    n = make_transport(cfg).push(local_shards, "shards")
    stats["pushed_files"] = n
    config.jsonl_append(config.path(cfg, "exchange") / "crawl_stats.jsonl", stats)
    heartbeat(cfg, "crawler", phase="idle", last=stats.get("crawl"))
    return stats


def run_forever(cfg: dict, interval_s: float = 600, **kw) -> None:
    gov = Governor(cfg, "crawler")
    while True:
        try:
            gov.tick()
            s = crawl_once(cfg, gov=gov, **kw)
            log.info(f"crawl round: {s.get('crawl')}")
            kw["open_data"] = False
            t_end = time.time() + interval_s
            while time.time() < t_end:
                gov.tick()
                heartbeat(cfg, "crawler", phase="sleep")
                time.sleep(1)
        except Halt as e:
            heartbeat(cfg, "crawler", phase="halted", reason=str(e))
            log.warning(f"halted: {e}")
            return
