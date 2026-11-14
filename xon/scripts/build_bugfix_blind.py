"""Second bug-fix set, written AFTER the repair tool was developed, and never used to tune it.
Report numbers on this set as the honest blind measurement."""
import json, subprocess, sys, tempfile
from pathlib import Path
OUT = Path(__file__).resolve().parent.parent / "evalsets" / "bugfix_blind.jsonl"
B = [
("total_price", "def total_price(items):\n    return sum(p * q for p, q in items) - 1\n", "def total_price(items):\n    return sum(p * q for p, q in items)\n", ["total_price([(2, 3), (1, 1)]) == 7"]),
("is_vowel", "def is_vowel(c):\n    return c.lower() in 'aeio'\n", "def is_vowel(c):\n    return c.lower() in 'aeiou'\n", ["is_vowel('u')", "is_vowel('A')", "not is_vowel('b')"]),
("pad", "def pad(s, n):\n    return s + ' ' * (n - len(s) - 1)\n", "def pad(s, n):\n    return s + ' ' * (n - len(s))\n", ["pad('ab', 4) == 'ab  '"]),
("clamp01", "def clamp01(x):\n    return max(0, min(0, x))\n", "def clamp01(x):\n    return max(0, min(1, x))\n", ["clamp01(0.5) == 0.5", "clamp01(2) == 1", "clamp01(-1) == 0"]),
("positive", "def positive(xs):\n    return [x for x in xs if x >= 0]\n", "def positive(xs):\n    return [x for x in xs if x > 0]\n", ["positive([-1, 0, 2]) == [2]"]),
("percent", "def percent(a, b):\n    return a / b * 10\n", "def percent(a, b):\n    return a / b * 100\n", ["percent(1, 4) == 25"]),
("halve", "def halve(xs):\n    return xs[:len(xs) // 3]\n", "def halve(xs):\n    return xs[:len(xs) // 2]\n", ["halve([1, 2, 3, 4]) == [1, 2]"]),
("both", "def both(a, b):\n    return a or b\n", "def both(a, b):\n    return a and b\n", ["both(True, True)", "not both(True, False)"]),
("tail", "def tail(xs):\n    return xs[2:]\n", "def tail(xs):\n    return xs[1:]\n", ["tail([1, 2, 3]) == [2, 3]"]),
("rem", "def rem(px):\n    return px / 10\n", "def rem(px):\n    return px / 16\n", ["rem(32) == 2"]),
("big", "def big(xs, t):\n    return [x for x in xs if x < t]\n", "def big(xs, t):\n    return [x for x in xs if x > t]\n", ["big([1, 5, 9], 4) == [5, 9]"]),
("area", "def area(w, h):\n    return w + h\n", "def area(w, h):\n    return w * h\n", ["area(3, 4) == 12"]),
("label", "def label(n):\n    return 'item' if n == 1 else 'item'\n", "def label(n):\n    return 'item' if n == 1 else 'items'\n", ["label(1) == 'item'", "label(2) == 'items'"]),
("steps", "def steps(n):\n    return list(range(0, n, 3))\n", "def steps(n):\n    return list(range(0, n, 2))\n", ["steps(6) == [0, 2, 4]"]),
("last_two", "def last_two(xs):\n    return xs[-3:]\n", "def last_two(xs):\n    return xs[-2:]\n", ["last_two([1, 2, 3]) == [2, 3]"]),
]
def ok(src, tests):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src + "\n" + "\n".join(f"assert {t}" for t in tests))
    return subprocess.run([sys.executable, f.name], capture_output=True).returncode == 0
if OUT.exists() and "--force" not in sys.argv:
    sys.exit("frozen")
rows = []
for i, (n, b, f, t) in enumerate(B):
    assert ok(f, t) and not ok(b, t), n
    rows.append({"id": f"xon-bugblind-{i:03d}", "entry": n, "buggy": b, "fixed": f, "tests": t, "license": "CC0-1.0"})
OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(len(rows))
