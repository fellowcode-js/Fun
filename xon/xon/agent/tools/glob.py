SPEC = {"name": "glob", "description": "List files matching a glob pattern inside the project.", "params": {"pattern": "str"}}


def run(ctx, pattern: str) -> dict:
    files = sorted(str(p.relative_to(ctx.root)) for p in ctx.root.glob(pattern)
                   if p.is_file() and ".git/" not in str(p) and "/.xon/" not in str(p))
    return {"ok": True, "files": files[:500], "count": len(files)}
