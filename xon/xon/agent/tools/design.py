"""All design.* tools behind one entry: from_prompt, from_screenshot, critique, palette, type, tokens."""
import json

SPEC = {"name": "design", "description": "design actions: from_prompt(prompt,out) | from_screenshot(path,out) | "
        "critique(path) | palette(base,dark) | type(base,ratio) | tokens(path,out)",
        "params": {"action": "str", "prompt": "str?", "path": "str?", "out": "str?", "base": "str?", "dark": "bool?", "ratio": "float?"}}


def run(ctx, action: str, prompt: str = "", path: str = "", out: str = "", base: str = "#2f5fd0", dark: bool = False,
        ratio: float = 1.25, interact: bool = False, engine: str = "spec", **_) -> dict:
    from xon.design import critique, from_prompt, palette, tokens
    from xon.design.render import Renderer
    if action == "palette":
        return {"ok": True, **palette.generate(base, dark)}
    if action == "type":
        return {"ok": True, **palette.type_scale(16, ratio)}
    if action == "from_prompt":
        try:
            pt = ctx.pretrained() if engine == "pretrained" else None
            if engine == "pretrained" and pt is None:
                return {"ok": False, "error": "no pretrained coder available"}
            res = from_prompt.generate(prompt, engine=engine, lm=pt)
        except from_prompt.Refused as e:
            return {"ok": False, "refused": True, "error": str(e)}
        outp = ctx.path(out or "index.html")
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(res["html"])
        shot = None
        try:
            with Renderer() as r:
                img = r.screenshot_html(res["html"], 640, 480)
            shot = outp.with_suffix(".png")
            img.save(shot)
        except Exception as e:
            return {"ok": True, "path": str(outp.relative_to(ctx.root)), "screenshot": None, "note": f"no browser: {e}"}
        return {"ok": True, "path": str(outp.relative_to(ctx.root)), "screenshot": str(shot.relative_to(ctx.root)), "engine": res["engine"]}
    if action == "critique":
        p = ctx.path(path)
        if p.suffix in (".html", ".htm"):
            try:
                rep = critique.critique_file(p, interact=interact)
            except Exception:
                rep = critique.critique_html(p.read_text())
            rep.pop("image", None)
        else:
            from PIL import Image
            rep = critique.critique_image(Image.open(p), ctx.vision())
        return {"ok": True, **rep}
    if action == "tokens":
        t = tokens.from_html(ctx.path(path).read_text())
        if out:
            ctx.path(out).write_text(json.dumps(t, indent=1))
        return {"ok": True, "tokens": t, "css": tokens.to_css(t)}
    if action == "from_screenshot":
        from PIL import Image
        from xon.design.from_screenshot import from_screenshot
        img = Image.open(ctx.path(path)).convert("RGB")
        with Renderer() as r:
            res = from_screenshot(img, ctx.vision(), r, steps=10)
        if out:
            ctx.path(out).write_text(res["html"])
        return {"ok": True, **{k: v for k, v in res.items() if k != "layout"}}
    return {"ok": False, "error": f"unknown design action {action}"}
