SPEC = {"name": "edit", "description": "Exact string replacement; old must occur exactly once.",
        "params": {"path": "str", "old": "str", "new": "str"}}


def run(ctx, path: str, old: str, new: str) -> dict:
    p = ctx.path(path)
    txt = p.read_text()
    n = txt.count(old)
    if n != 1:
        return {"ok": False, "error": f"old text occurs {n} times in {path} (must be exactly 1)"}
    p.write_text(txt.replace(old, new, 1))
    return {"ok": True, "path": path}
