import os
import subprocess
import sys
import time

import pytest

from xon.nodes.transport import FolderTransport
from xon.pipeline.store import ShardWriter


def test_folder_push_pull(tmp_path):
    w = ShardWriter(tmp_path / "local", "t", max_records=2)
    for i in range(5):
        w.add({"kind": "text", "text": f"hello {i} " * 10})
    w.close()
    tr = FolderTransport(tmp_path / "exchange")
    assert tr.push(tmp_path / "local", "shards") == 4  # 3 shards + manifest
    assert tr.pull("shards", tmp_path / "remote") == 4
    assert tr.pull("shards", tmp_path / "remote") == 1  # only the manifest refreshes; shards are immutable


@pytest.mark.slow
def test_m3_crawler_and_trainer_processes_share_a_folder(tmp_path):
    """Crawler and trainer as separate OS processes, talking only through the exchange folder."""
    env = {**os.environ, "XON_HOME": str(tmp_path)}
    (tmp_path / "evalsets").symlink_to(os.path.join(os.path.dirname(__file__), "..", "evalsets"))
    crawler = subprocess.Popen([sys.executable, "-c",
                                "from xon import config; from xon.nodes.crawler_node import crawl_once; "
                                "crawl_once(config.load(), mock=True, max_pages=60, online_open=False)"], env=env, cwd=tmp_path)
    trainer = subprocess.Popen([sys.executable, "-c",
                                "from xon import config; from xon.nodes.trainer_node import run; "
                                "r=run(config.load(), cycles=1, wait_for_data_s=300, quick=True); "
                                "import json; print('RESULT', json.dumps(r[0]['data']))"], env=env, cwd=tmp_path,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert crawler.wait(timeout=600) == 0
    out, _ = trainer.communicate(timeout=1800)
    assert trainer.returncode == 0, out[-3000:]
    line = [l for l in out.splitlines() if l.startswith("RESULT")][-1]
    assert '"new_records": 0' not in line, line
    hb = {p.stem for p in (tmp_path / "exchange" / "heartbeats").glob("*.json")}
    assert {"crawler", "trainer"} <= hb
