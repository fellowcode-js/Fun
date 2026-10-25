import gzip

from xon.pipeline import clean_code, clean_images, clean_text
from xon.pipeline.store import EvalGuard, Manifest, ShardWriter, iter_records, prune_cold


def test_pii_and_secret_scrub():
    t, c = clean_text.scrub_pii("mail jane@x.org, call +1 (555) 123-4567, key sk-ABCDEFGHIJKLMNOP1234, 12 Oak Street. "
                                'password = "hunter2hunter2"')
    assert "jane@x.org" not in t and "555" not in t and "sk-ABC" not in t and "Oak Street" not in t and "hunter2" not in t
    assert c["EMAIL"] == 1 and c["PHONE"] == 1 and c["ADDRESS"] == 1 and c["SECRET"] == 2


def test_unsafe_quarantined_and_quality():
    t, st, _ = clean_text.clean("explicit porn content " * 10)
    assert t is None and st == "quarantine:unsafe_adult"
    assert clean_text.clean("too short")[1] == "reject:too_short"
    good = "Python lists are ordered, mutable sequences. They support slicing, sorting and comprehensions. " * 2
    assert clean_text.clean(good)[1] == "ok"
    assert clean_text.clean("same line\n" * 30)[1].startswith("reject")


def test_code_filters_and_near_dedupe():
    code = "def f(x):\n    return x + 1\n\n\ndef g(y):\n    return y * 2\n"
    assert clean_code.reject_reason(code, "python", "MIT") is None
    assert clean_code.reject_reason(code, "python", "GPL-3.0").startswith("license")
    assert clean_code.reject_reason("x=1;" * 400, "javascript", "MIT") == "minified"
    assert clean_code.reject_reason("# @generated do not edit\n" + code, "python", "MIT") == "generated"
    d = clean_code.MinHashDeduper()
    big = "\n".join(f"def func_{i}(a, b):\n    return a * {i} + b" for i in range(30))
    assert d.add(big)
    assert not d.add(big.replace("func_29", "func_x"))  # near duplicate
    assert d.add("\n".join(f"class C{i}:\n    value = '{i * 7}'" for i in range(30)))


def test_image_clean_and_phash_dedupe():
    import io
    from PIL import Image
    from xon.datasets.shapes import make
    img = make(1)[0]
    b = io.BytesIO()
    img.save(b, format="PNG")
    rec, st = clean_images.clean(b.getvalue(), "a red star", "CC0-1.0")
    assert st == "ok" and rec["ahash"]
    assert clean_images.clean(b.getvalue(), "portrait of a woman", "CC-BY")[1] == "reject:private_person"
    assert clean_images.clean(b.getvalue(), "nsfw xxx", "CC-BY")[1].startswith("quarantine")
    d = clean_images.PHashDeduper()
    assert d.add(rec["ahash"]) and not d.add(rec["ahash"])


def test_shards_manifest_evalguard_prune(tmp_path, home):
    from xon import config
    guard = EvalGuard(config.path(home, "evalsets"))
    import json
    prob = json.loads((config.path(home, "evalsets") / "code_problems.jsonl").read_text().splitlines()[0])
    w = ShardWriter(tmp_path / "s", "t", max_records=3, guard=guard)
    assert not w.add({"kind": "code", "code": prob["solution"]}), "eval solution leaked into training"
    for i in range(7):
        w.add({"kind": "text", "text": f"record number {i} " * 5, "license": "MIT"})
    names = w.close()
    assert len(names) == 3 and w.dropped_eval == 1
    m = Manifest(tmp_path / "s").load()
    assert sum(s["n"] for s in m["shards"]) == 7 and all(len(s["sha256"]) == 64 for s in m["shards"])
    assert len(list(iter_records(tmp_path / "s"))) == 7
    assert not list((tmp_path / "s").glob("*.part"))
    removed = prune_cold(tmp_path / "s", keep_names={names[0]}, target_bytes=0)
    assert names[0] not in removed and len(removed) == 2
    assert (tmp_path / "s" / names[0]).exists()
