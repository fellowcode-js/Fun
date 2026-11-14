SPEC = {"name": "glob", "description": "List files matching a glob pattern inside the project.", "params": {"pattern": "str"}}


def run(ctx, pattern: str) -> dict:
    files = sorted(str(p.relative_to(ctx.root)) for p in ctx.root.glob(pattern)
                   if p.is_file() and not {".git", ".xon"} & set(p.relative_to(ctx.root).parts))
    return {"ok": True, "files": files[:500], "count": len(files)}
