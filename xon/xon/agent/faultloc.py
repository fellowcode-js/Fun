"""Spectrum-based fault localization (Ochiai) as a pytest plugin: `pytest -p xon.agent.faultloc`.

Records which project source lines each test executes, plus pass/fail, into $XON_FAULTLOC_OUT.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

_ROOT = os.environ.get("XON_FAULTLOC_ROOT", os.getcwd())
_OUT = os.environ.get("XON_FAULTLOC_OUT", "")
_cov: dict[str, set] = {}
_res: dict[str, bool] = {}
_cur: set | None = None


def _tracer(frame, event, arg):
    f = frame.f_code.co_filename
    if not f.startswith(_ROOT) or "/tests/" in f or os.path.basename(f).startswith("test_") or "site-packages" in f:
        return None if event == "call" else _tracer
    if event == "line" and _cur is not None:
        _cur.add((os.path.relpath(f, _ROOT), frame.f_lineno))
    return _tracer


def pytest_runtest_call(item):
    global _cur
    _cur = set()
    sys.settrace(_tracer)


def pytest_runtest_teardown(item):
    global _cur
    sys.settrace(None)
    if _cur is not None:
        _cov[item.nodeid] = _cur
    _cur = None


def pytest_runtest_logreport(report):
    if report.when == "call":
        _res[report.nodeid] = report.passed


def pytest_sessionfinish(session):
    if _OUT:
        Path(_OUT).write_text(json.dumps({"cov": {k: sorted(v) for k, v in _cov.items()}, "res": _res}))


def ochiai(data: dict) -> list[tuple[str, int, float]]:
    cov, res = data["cov"], data["res"]
    total_failed = sum(1 for v in res.values() if not v)
    ef, ep = {}, {}
    for t, lines in cov.items():
        failed = not res.get(t, True)
        for f, l in lines:
            k = (f, l)
            if failed:
                ef[k] = ef.get(k, 0) + 1
            else:
                ep[k] = ep.get(k, 0) + 1
    scores = []
    for k in set(ef) | set(ep):
        e_f, e_p = ef.get(k, 0), ep.get(k, 0)
        d = math.sqrt(total_failed * (e_f + e_p))
        if d and e_f:
            scores.append((k[0], k[1], e_f / d))
    scores.sort(key=lambda s: -s[2])
    return scores
