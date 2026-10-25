"""Project memory: XON.md (or AGENTS.md) loaded every session; notes appended under '## Notes'."""
from __future__ import annotations

import time
from pathlib import Path


def load(root: Path) -> str:
    for name in ("XON.md", "AGENTS.md"):
        p = Path(root) / name
        if p.exists():
            return p.read_text()
    return ""


def remember(root: Path, note: str) -> None:
    p = Path(root) / "XON.md"
    txt = p.read_text() if p.exists() else "# XON project memory\n"
    if "## Notes" not in txt:
        txt += "\n## Notes\n"
    txt += f"- {time.strftime('%Y-%m-%d')}: {note}\n"
    p.write_text(txt)
