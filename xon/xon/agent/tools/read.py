SPEC = {"name": "read", "description": "Read a text file (optionally a line range).",
        "params": {"path": "str", "start": "int?", "end": "int?"}}


def run(ctx, path: str, start: int = 1, end: int | None = None) -> dict:
    p = ctx.path(path)
    lines = p.read_text(errors="replace").splitlines()
    end = end or len(lines)
    body = "\n".join(f"{i:5d}  {l}" for i, l in enumerate(lines[start - 1:end], start))
    return {"ok": True, "path": path, "lines": len(lines), "content": body[:60000]}
