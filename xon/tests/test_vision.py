import torch

from xon.datasets import shapes
from xon.vision.model import VisionConfig, XONVision
from xon.vision.ui_detect import DET_H, DET_W, decode, encode_targets, iou, match


def test_detection_target_roundtrip():
    boxes = [{"label": "button", "x": 100, "y": 200, "w": 120, "h": 40}, {"label": "nav", "x": 0, "y": 0, "w": 640, "h": 50}]
    cls, reg = encode_targets(boxes, 640, 480)
    # build a perfect network output from the targets and decode it back
    out = torch.full((12, cls.shape[0], cls.shape[1]), -10.0)
    for gy in range(cls.shape[0]):
        for gx in range(cls.shape[1]):
            out[int(cls[gy, gx]), gy, gx] = 10.0
    out[8:] = reg
    dets = decode(out, 640, 480)
    m = match(dets, boxes)
    assert m["tp"] == 2 and m["fn"] == 0
    assert iou((0, 0, 10, 10), (5, 0, 10, 10)) == 1 / 3


def test_vision_heads_shapes():
    m = XONVision(VisionConfig(n_classes=len(shapes.SHAPES)))
    x = torch.randn(2, 3, 64, 64)
    assert m.classify(x).shape == (2, 10)
    from xon.datasets.synth_ui import UI_CLASSES
    assert m.detect_raw(torch.randn(1, 3, DET_H, DET_W)).shape == (1, len(UI_CLASSES) + 5, DET_H // 8, DET_W // 8)
    assert m.zero_shot(x, shapes.SHAPES).shape == (2, 10)
    loss = m.contrastive_loss(x, ["a red star", "a blue circle"])
    assert torch.isfinite(loss)


def test_short_training_beats_chance(tmp_path):
    from xon.vision import train
    pairs = []
    for s in range(400):
        img, sh, _, cap = shapes.make(s)
        pairs.append({"image": img, "caption": cap, "label": shapes.SHAPES.index(sh)})
    train.train(pairs, [], tmp_path, minutes=10, max_steps=120)
    m = train.load_model(tmp_path / "vision.pt")
    from xon.vision.train import to_tensor
    xs, ys = [], []
    for s in range(50_000, 50_200):
        img, sh, _, _ = shapes.make(s)
        xs.append(to_tensor(img, (64, 64)))
        ys.append(shapes.SHAPES.index(sh))
    acc = (m.classify(torch.stack(xs)).argmax(-1) == torch.tensor(ys)).float().mean().item()
    assert acc > 0.3, acc  # chance is 0.1
