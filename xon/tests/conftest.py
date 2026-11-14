import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def home(tmp_path, monkeypatch):
    """An isolated XON_HOME with the frozen eval sets linked in."""
    monkeypatch.setenv("XON_HOME", str(tmp_path))
    for k in ("XON_CHECKPOINTS", "XON_DATA", "XON_EXCHANGE"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "evalsets").symlink_to(ROOT / "evalsets")
    from xon import config
    return config.load(tmp_path)


def browser_available() -> bool:
    try:
        from xon.design.render import available
        return available()
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not browser_available(), reason="no headless Chromium (playwright install chromium)")
