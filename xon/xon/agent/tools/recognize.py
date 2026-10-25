from PIL import Image

SPEC = {"name": "recognize", "description": "Classify an image (top-5) and zero-shot against given labels.",
        "params": {"path": "str", "labels": "list?"}}


def run(ctx, path: str, labels: list | None = None) -> dict:
    vm = ctx.vision()
    if vm is None:
        return {"ok": False, "error": "no promoted vision model; run `xon train` first"}
    from xon.vision import predict
    img = Image.open(ctx.path(path)).convert("RGB")
    out = {"ok": True, "top5": predict.classify(vm, img)}
    out["zero_shot"] = predict.zero_shot(vm, img, labels)[:5] if labels else predict.zero_shot(vm, img)[:5]
    return out
