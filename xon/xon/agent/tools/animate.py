"""animate: description -> looping animation (SVG/CSS page + GIF), made locally by xon.design.animate."""
SPEC = {"name": "animate", "description": "Make a looping animation from a description (subject, motion, colour, speed), "
        "e.g. 'a red ball bouncing' or 'a stick figure waving'. Writes <out>.html (SVG + CSS) and <out>.gif and "
        "self-checks that it moves and stays on stage.",
        "params": {"prompt": "str", "out": "str?"}}


def run(ctx, prompt: str, out: str = "animation", **_) -> dict:
    from xon.design.animate import make
    base = ctx.path(out)
    r = make(prompt, base)
    if r.get("ok"):
        for k in ("html", "gif"):
            r[k] = str(__import__("pathlib").Path(r[k]).relative_to(ctx.root))
    return r
