"""Build xon.zip: code, docs, frozen evalsets, tiny samples, screenshots. No scraped data, no checkpoints."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {"checkpoints", "exchange", "logs", "artifacts", ".xon", "__pycache__", ".pytest_cache", "xon.egg-info", ".venv"}
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "xon.zip"


def include(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    if set(rel.parts) & EXCLUDE_DIRS or p.suffix in (".pyc",) or p.name in ("STOP", "xon.toml"):
        return False
    if rel.parts[0] == "data":
        return len(rel.parts) > 1 and rel.parts[1] == "samples"
    return p.is_file()


files = sorted(p for p in ROOT.rglob("*") if include(p))
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, Path("xon") / f.relative_to(ROOT))
    for d in ("checkpoints", "artifacts"):
        z.writestr(f"xon/{d}/.keep", "")
size = OUT.stat().st_size / 1e6
print(f"wrote {OUT} ({len(files)} files, {size:.1f} MB)")
