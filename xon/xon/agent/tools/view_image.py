from PIL import Image

SPEC = {"name": "view_image", "description": "Describe an image: size, dominant colors, detected UI elements.",
        "params": {"path": "str"}}


def run(ctx, path: str) -> dict:
    img = Image.open(ctx.path(path)).convert("RGB")
    small = img.resize((32, 32))
    colors = sorted(small.getcolors(1024) or [], reverse=True)[:5]
    out = {"ok": True, "size": img.size, "dominant": ["#%02x%02x%02x" % c for _, c in colors]}
    vm = ctx.vision()
    if vm is not None:
        from xon.vision.predict import detect
        dets = detect(vm, img)
        out["ui_elements"] = [{k: (round(v) if isinstance(v, float) and k != "score" else v) for k, v in d.items()} for d in dets[:40]]
    else:
        out["note"] = "no promoted vision model yet; run `xon train`"
    return out
