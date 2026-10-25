import re

SPEC = {"name": "grep", "description": "Regex search over files (glob filter).", "params": {"pattern": "str", "glob": "str?"}}


def run(ctx, pattern: str, glob: str = "**/*.py") -> dict:
    rx = re.compile(pattern)
    hits = []
    for p in sorted(ctx.root.glob(glob)):
        if not p.is_file() or ".git" in p.parts or ".xon" in p.parts:
            continue
        try:
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{p.relative_to(ctx.root)}:{i}: {line.strip()[:200]}")
                    if len(hits) >= 300:
                        return {"ok": True, "hits": hits, "truncated": True}
        except OSError:
            pass
    return {"ok": True, "hits": hits}
