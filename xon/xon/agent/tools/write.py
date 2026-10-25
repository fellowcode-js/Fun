SPEC = {"name": "write", "description": "Create or overwrite a file with content.", "params": {"path": "str", "content": "str"}}


def run(ctx, path: str, content: str) -> dict:
    p = ctx.path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(content)
    return {"ok": True, "path": path, "bytes": len(content), "created": not existed}
