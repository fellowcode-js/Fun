SPEC = {"name": "complete", "description": "Fill-in-the-middle code completion with the local XON LM.",
        "params": {"prefix": "str", "suffix": "str?", "max_new": "int?"}}


def run(ctx, prefix: str, suffix: str = "", max_new: int = 64) -> dict:
    m, tok = ctx.lm()
    if m is None:
        return {"ok": False, "error": "no promoted XON LM; run `xon train` first"}
    from xon.lm.generate import complete, fill_in_middle
    text = fill_in_middle(m, tok, prefix, suffix, max_new=max_new) if suffix else complete(m, tok, prefix, max_new=max_new, temperature=0.2)
    return {"ok": True, "completion": text, "model": "XON LM (local)"}
