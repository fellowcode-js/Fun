from xon.trainer.promote import Registry, decide

BEST = {"code_ppl": 20.0, "code_pass@1": 0.0, "ui_f1": 0.40, "recog_top1": 0.90, "design_fidelity": 0.80, "bugfix_rate": 0.9}


def test_first_candidate_promotes():
    assert decide(BEST, None)["promote"]


def test_better_candidate_promotes():
    c = {**BEST, "code_ppl": 18.0, "ui_f1": 0.45}
    d = decide(c, BEST)
    assert d["promote"] and "code_ppl" in d["reason"]


def test_noise_level_change_is_rolled_back():
    c = {**BEST, "code_ppl": 19.99}
    d = decide(c, BEST)
    assert not d["promote"] and "noise margin" in d["reason"]


def test_deliberately_bad_checkpoint_rejected():
    c = {**BEST, "code_ppl": 15.0, "recog_top1": 0.50}  # better LM, broken vision
    d = decide(c, BEST)
    assert not d["promote"] and "recog_top1" in d["reason"]


def test_registry_promote_atomic(tmp_path):
    r = Registry(tmp_path)
    f = tmp_path / "lm.bin"
    f.write_bytes(b"weights")
    r.promote({"lm.pt": f}, BEST, cycle=1)
    assert (r.promoted / "lm.pt").read_bytes() == b"weights" and r.best_metrics()["cycle"] == 1
    f.write_bytes(b"v2")
    r.promote({"lm.pt": f}, {**BEST, "code_ppl": 10}, cycle=2)
    assert (r.promoted / "lm.pt").read_bytes() == b"v2" and not list(tmp_path.glob(".stage-*"))


def test_components_promote_independently():
    from xon.trainer.promote import decide_components
    c = {**BEST, "code_ppl": 30.0, "ui_f1": 0.55, "recog_top1": 0.99}  # LM regressed, vision improved
    d = decide_components(c, BEST)
    assert not d["lm"]["promote"] and d["vision"]["promote"]


def test_registry_carries_over_unpromoted_files(tmp_path):
    r = Registry(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"lm1")
    b.write_bytes(b"vis1")
    r.promote({"lm.pt": a, "vision.pt": b}, BEST, 1)
    b.write_bytes(b"vis2")
    r.promote({"vision.pt": b}, BEST, 2)
    assert (r.promoted / "lm.pt").read_bytes() == b"lm1" and (r.promoted / "vision.pt").read_bytes() == b"vis2"


def test_tiny_rate_changes_are_noise_not_regressions():
    best = {**BEST, "code_pass@1": 0.0032}
    c = {**best, "code_pass@1": 0.0, "code_ppl": 18.0}
    d = decide(c, best)
    assert d["promote"], d
