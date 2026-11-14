from xon.design.animate import Refused, check, frames, html, make, parse
import pytest


def test_parse():
    s = parse("three yellow stars spinning slowly on a dark background")
    assert (s.subject, s.count, s.motions, s.color, s.duration) == ("star", 3, ["spin"], "#ffc53d", 3.0)
    assert parse("a stick figure waving hello").motions == ["wave"]
    assert parse("a person walking").subject == "stickman"
    assert parse("loading dots").count == 3
    assert parse("the word 'HI' floating").text == "HI"
    assert parse("a black ball bouncing on a black background").background != "#1c1c1c"  # kept visible
    with pytest.raises(Refused):
        parse("mario jumping")


@pytest.mark.parametrize("prompt", ["a red ball bouncing", "a stick figure walking", "a person waving hello",
                                    "loading dots in purple", "a pink heart beating", "a blue spinner", "a square shaking",
                                    "the word 'XON' floating", "two rings orbiting", "a green triangle sliding"])
def test_every_subject_moves_and_stays_on_stage(prompt):
    fr, ms = frames(parse(prompt))
    qc = check(fr)
    assert qc["moves"] and not qc["touches_edge"], (prompt, qc)
    assert 10 <= ms <= 200


def test_outputs(tmp_path):
    r = make("a red ball bouncing", tmp_path / "ball")
    assert r["ok"] and (tmp_path / "ball.gif").read_bytes()[:6] == b"GIF89a"
    page = (tmp_path / "ball.html").read_text()
    assert "@keyframes a0" in page and "prefers-reduced-motion" in page and "<svg" in page
    assert "<polyline" in html(parse("a stick figure walking"))
