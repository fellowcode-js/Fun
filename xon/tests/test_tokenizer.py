from xon.tokenizer import BPETokenizer


def test_roundtrip_and_specials():
    texts = ["def add(a, b):\n    return a + b\n" * 20, '<div class="card"><button>Go</button></div>' * 20]
    tok = BPETokenizer.train(texts, vocab_size=600)
    for s in ['<div class="x">héllo</div>', "def f():\n    return 1\n", "<|fim_prefix|>a<|fim_suffix|>b<|fim_middle|>"]:
        assert tok.decode(tok.encode(s)) == s
    ids = tok.encode("<|fim_prefix|>x")
    assert ids[0] == tok.special("<|fim_prefix|>")
    assert len(tok.encode("<div")) == 1  # HTML-aware atomic token
    assert tok.vocab_size <= 600


def test_save_load(tmp_path):
    tok = BPETokenizer.train(["hello world " * 50], vocab_size=400)
    tok.save(tmp_path / "t.json")
    t2 = BPETokenizer.load(tmp_path / "t.json")
    assert t2.encode("hello world") == tok.encode("hello world")
