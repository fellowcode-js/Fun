"""Build XON's FROZEN eval sets. Run once; output lives in evalsets/ and is never overwritten by crawling.

All problems below were written for XON (license: CC0). Re-running refuses to overwrite existing files
unless --force is given.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evalsets"

# (name, signature, docstring, solution body, tests)
P = [
("add_two", "a, b", "Return a + b.", "return a + b", ["f(1, 2) == 3", "f(-1, 1) == 0", "f(10, 5) == 15"]),
("square", "x", "Return x squared.", "return x * x", ["f(3) == 9", "f(-4) == 16", "f(0) == 0"]),
("is_even", "n", "Return True if n is even.", "return n % 2 == 0", ["f(2)", "not f(3)", "f(0)"]),
("max_of_list", "xs", "Return the largest element of a non-empty list.", "return max(xs)", ["f([1, 5, 3]) == 5", "f([-2, -9]) == -2"]),
("min_of_list", "xs", "Return the smallest element of a non-empty list.", "return min(xs)", ["f([4, 2, 8]) == 2", "f([7]) == 7"]),
("sum_list", "xs", "Return the sum of the numbers in xs.", "return sum(xs)", ["f([1, 2, 3]) == 6", "f([]) == 0"]),
("reverse_string", "s", "Return s reversed.", "return s[::-1]", ["f('abc') == 'cba'", "f('') == ''"]),
("count_char", "s, c", "Count occurrences of character c in s.", "return s.count(c)", ["f('banana', 'a') == 3", "f('xyz', 'a') == 0"]),
("factorial", "n", "Return n! for n >= 0.", "r = 1\n    for i in range(2, n + 1):\n        r *= i\n    return r", ["f(0) == 1", "f(5) == 120", "f(1) == 1"]),
("fibonacci", "n", "Return the n-th Fibonacci number with f(0)=0, f(1)=1.", "a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a", ["f(0) == 0", "f(1) == 1", "f(10) == 55"]),
("is_palindrome", "s", "Return True if s reads the same backwards.", "return s == s[::-1]", ["f('racecar')", "not f('abc')", "f('')"]),
("count_vowels", "s", "Count the vowels (aeiou, case-insensitive) in s.", "return sum(1 for c in s.lower() if c in 'aeiou')", ["f('Hello') == 2", "f('xyz') == 0", "f('AEIOU') == 5"]),
("celsius_to_f", "c", "Convert Celsius to Fahrenheit.", "return c * 9 / 5 + 32", ["f(0) == 32", "f(100) == 212"]),
("abs_value", "x", "Return the absolute value of x without using abs().", "return -x if x < 0 else x", ["f(-3) == 3", "f(4) == 4", "f(0) == 0"]),
("clamp", "x, lo, hi", "Clamp x into the range [lo, hi].", "return max(lo, min(hi, x))", ["f(5, 0, 10) == 5", "f(-1, 0, 10) == 0", "f(11, 0, 10) == 10"]),
("first_char", "s", "Return the first character of s, or '' if s is empty.", "return s[:1]", ["f('hello') == 'h'", "f('') == ''"]),
("last_element", "xs", "Return the last element of xs, or None if empty.", "return xs[-1] if xs else None", ["f([1, 2, 3]) == 3", "f([]) is None"]),
("average", "xs", "Return the mean of a non-empty list of numbers.", "return sum(xs) / len(xs)", ["f([1, 2, 3]) == 2", "f([5]) == 5"]),
("dedupe", "xs", "Remove duplicates from xs, keeping first occurrences in order.", "seen = set()\n    out = []\n    for x in xs:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out", ["f([1, 2, 1, 3, 2]) == [1, 2, 3]", "f([]) == []"]),
("flatten", "xss", "Flatten a list of lists by one level.", "return [x for xs in xss for x in xs]", ["f([[1, 2], [3]]) == [1, 2, 3]", "f([]) == []"]),
("word_count", "s", "Return the number of whitespace-separated words in s.", "return len(s.split())", ["f('a b  c') == 3", "f('') == 0"]),
("capitalize_words", "s", "Capitalize the first letter of every word, words separated by single spaces.", "return ' '.join(w[:1].upper() + w[1:] for w in s.split(' '))", ["f('hello world') == 'Hello World'", "f('a') == 'A'"]),
("is_prime", "n", "Return True if n is a prime number.", "if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True", ["f(2)", "f(13)", "not f(1)", "not f(15)"]),
("gcd", "a, b", "Return the greatest common divisor of a and b.", "while b:\n        a, b = b, a % b\n    return abs(a)", ["f(12, 18) == 6", "f(7, 3) == 1", "f(0, 5) == 5"]),
("lcm", "a, b", "Return the least common multiple of positive a and b.", "import math\n    return a * b // math.gcd(a, b)", ["f(4, 6) == 12", "f(3, 5) == 15"]),
("digit_sum", "n", "Return the sum of the decimal digits of a non-negative integer n.", "return sum(int(d) for d in str(n))", ["f(123) == 6", "f(0) == 0", "f(999) == 27"]),
("count_positive", "xs", "Count the numbers in xs that are > 0.", "return sum(1 for x in xs if x > 0)", ["f([1, -2, 3, 0]) == 2", "f([]) == 0"]),
("filter_even", "xs", "Return the even numbers of xs in order.", "return [x for x in xs if x % 2 == 0]", ["f([1, 2, 3, 4]) == [2, 4]", "f([1]) == []"]),
("square_all", "xs", "Return a list with every element squared.", "return [x * x for x in xs]", ["f([1, 2, 3]) == [1, 4, 9]", "f([]) == []"]),
("join_with_comma", "xs", "Join a list of strings with ', '.", "return ', '.join(xs)", ["f(['a', 'b']) == 'a, b'", "f([]) == ''"]),
("char_frequency", "s", "Return a dict mapping each character in s to its count.", "d = {}\n    for c in s:\n        d[c] = d.get(c, 0) + 1\n    return d", ["f('aab') == {'a': 2, 'b': 1}", "f('') == {}"]),
("merge_dicts", "a, b", "Return a new dict with keys of a and b; b wins on conflicts.", "return {**a, **b}", ["f({'x': 1}, {'y': 2}) == {'x': 1, 'y': 2}", "f({'x': 1}, {'x': 3}) == {'x': 3}"]),
("invert_dict", "d", "Swap keys and values of a dict with unique values.", "return {v: k for k, v in d.items()}", ["f({'a': 1, 'b': 2}) == {1: 'a', 2: 'b'}", "f({}) == {}"]),
("second_largest", "xs", "Return the second largest distinct value in xs (at least two distinct values).", "return sorted(set(xs))[-2]", ["f([1, 3, 2]) == 2", "f([5, 5, 4]) == 4"]),
("running_sum", "xs", "Return the list of running (prefix) sums.", "out, t = [], 0\n    for x in xs:\n        t += x\n        out.append(t)\n    return out", ["f([1, 2, 3]) == [1, 3, 6]", "f([]) == []"]),
("chunk", "xs, n", "Split xs into consecutive chunks of size n (last may be shorter).", "return [xs[i:i + n] for i in range(0, len(xs), n)]", ["f([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]", "f([], 3) == []"]),
("rotate_left", "xs, k", "Rotate list xs left by k positions.", "if not xs:\n        return []\n    k %= len(xs)\n    return xs[k:] + xs[:k]", ["f([1, 2, 3, 4], 1) == [2, 3, 4, 1]", "f([1, 2], 3) == [2, 1]", "f([], 2) == []"]),
("binary_string", "n", "Return the binary representation of non-negative n without prefix.", "return bin(n)[2:]", ["f(5) == '101'", "f(0) == '0'"]),
("from_binary", "s", "Parse a binary string into an int.", "return int(s, 2)", ["f('101') == 5", "f('0') == 0"]),
("count_words_starting", "s, ch", "Count words in s that start with character ch.", "return sum(1 for w in s.split() if w.startswith(ch))", ["f('apple ant bee', 'a') == 2", "f('', 'a') == 0"]),
("remove_spaces", "s", "Remove all space characters from s.", "return s.replace(' ', '')", ["f('a b c') == 'abc'", "f('') == ''"]),
("is_sorted", "xs", "Return True if xs is sorted in non-decreasing order.", "return all(a <= b for a, b in zip(xs, xs[1:]))", ["f([1, 2, 2, 3])", "not f([2, 1])", "f([])"]),
("index_of", "xs, x", "Return the index of x in xs, or -1 if absent.", "return xs.index(x) if x in xs else -1", ["f([4, 5, 6], 5) == 1", "f([], 1) == -1"]),
("pairs_sum", "xs, target", "Return True if two different positions in xs sum to target.", "seen = set()\n    for x in xs:\n        if target - x in seen:\n            return True\n        seen.add(x)\n    return False", ["f([1, 2, 3], 5)", "not f([1, 2], 5)", "not f([], 0)"]),
("title_case", "s", "Return s in title case using str.title().", "return s.title()", ["f('hi there') == 'Hi There'"]),
("hex_color", "r, g, b", "Return a lowercase CSS hex color like '#ff0000' for 0-255 r, g, b.", "return '#%02x%02x%02x' % (r, g, b)", ["f(255, 0, 0) == '#ff0000'", "f(0, 128, 255) == '#0080ff'"]),
("parse_hex_color", "s", "Parse '#rrggbb' into an (r, g, b) tuple of ints.", "s = s.lstrip('#')\n    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))", ["f('#ff0000') == (255, 0, 0)", "f('#0080ff') == (0, 128, 255)"]),
("px_to_rem", "px, base=16", "Convert pixels to rem given a base font size.", "return px / base", ["f(32) == 2", "f(8, base=8) == 1"]),
("css_rule", "selector, props", "Return a CSS rule string 'sel { k: v; k2: v2; }' from a dict of props in insertion order.", "body = ' '.join(f'{k}: {v};' for k, v in props.items())\n    return f'{selector} {{ {body} }}'", ["f('.btn', {'color': 'red'}) == '.btn { color: red; }'", "f('a', {'x': '1', 'y': '2'}) == 'a { x: 1; y: 2; }'"]),
("html_tag", "tag, text", "Return '<tag>text</tag>'.", "return f'<{tag}>{text}</{tag}>'", ["f('p', 'hi') == '<p>hi</p>'", "f('b', '') == '<b></b>'"]),
("escape_html", "s", "Escape &, <, > in s as HTML entities.", "return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')", ["f('<a&b>') == '&lt;a&amp;b&gt;'", "f('x') == 'x'"]),
("strip_tags", "s", "Remove anything between < and > (inclusive) from s.", "import re\n    return re.sub(r'<[^>]*>', '', s)", ["f('<b>hi</b>') == 'hi'", "f('plain') == 'plain'"]),
("snake_to_camel", "s", "Convert snake_case to camelCase.", "parts = s.split('_')\n    return parts[0] + ''.join(p.title() for p in parts[1:])", ["f('hello_world') == 'helloWorld'", "f('a') == 'a'"]),
("camel_to_snake", "s", "Convert camelCase to snake_case.", "import re\n    return re.sub(r'([A-Z])', lambda m: '_' + m.group(1).lower(), s)", ["f('helloWorld') == 'hello_world'", "f('a') == 'a'"]),
("kebab_case", "s", "Convert a space-separated phrase to lowercase kebab-case.", "return '-'.join(s.lower().split())", ["f('Primary Button') == 'primary-button'", "f('x') == 'x'"]),
("truncate", "s, n", "Return s cut to n chars with '...' appended if it was longer than n.", "return s if len(s) <= n else s[:n] + '...'", ["f('hello', 10) == 'hello'", "f('hello world', 5) == 'hello...'"]),
("matrix_transpose", "m", "Transpose a rectangular list-of-lists matrix.", "return [list(r) for r in zip(*m)]", ["f([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]", "f([[1, 2, 3]]) == [[1], [2], [3]]"]),
("count_unique", "xs", "Return the number of distinct elements.", "return len(set(xs))", ["f([1, 1, 2]) == 2", "f([]) == 0"]),
("power_of_two", "n", "Return True if n is a positive power of two.", "return n > 0 and n & (n - 1) == 0", ["f(1)", "f(64)", "not f(0)", "not f(12)"]),
("nth_word", "s, n", "Return the n-th (0-based) whitespace-separated word, or '' if out of range.", "w = s.split()\n    return w[n] if 0 <= n < len(w) else ''", ["f('a b c', 1) == 'b'", "f('a', 5) == ''"]),
("grid_columns", "n", "Return a CSS grid-template-columns value repeating n equal columns, e.g. 'repeat(3, 1fr)'.", "return f'repeat({n}, 1fr)'", ["f(3) == 'repeat(3, 1fr)'", "f(1) == 'repeat(1, 1fr)'"]),
("spacing_scale", "base, n", "Return the first n values of a doubling spacing scale starting at base.", "return [base * 2 ** i for i in range(n)]", ["f(4, 4) == [4, 8, 16, 32]", "f(8, 0) == []"]),
]

BUGS = [  # (name, buggy, fixed, tests) -- each bug is a small, realistic slip
("sum_to_n", "def sum_to_n(n):\n    total = 0\n    for i in range(n):\n        total += i\n    return total\n", "def sum_to_n(n):\n    total = 0\n    for i in range(n + 1):\n        total += i\n    return total\n", ["sum_to_n(3) == 6", "sum_to_n(0) == 0"]),
("is_adult", "def is_adult(age):\n    return age > 18\n", "def is_adult(age):\n    return age >= 18\n", ["is_adult(18)", "not is_adult(17)"]),
("last_item", "def last_item(xs):\n    return xs[len(xs)]\n", "def last_item(xs):\n    return xs[len(xs) - 1]\n", ["last_item([1, 2, 3]) == 3"]),
("average", "def average(xs):\n    return sum(xs) / (len(xs) + 1)\n", "def average(xs):\n    return sum(xs) / len(xs)\n", ["average([2, 4]) == 3"]),
("max_val", "def max_val(xs):\n    m = xs[0]\n    for x in xs:\n        if x < m:\n            m = x\n    return m\n", "def max_val(xs):\n    m = xs[0]\n    for x in xs:\n        if x > m:\n            m = x\n    return m\n", ["max_val([1, 5, 3]) == 5"]),
("count_even", "def count_even(xs):\n    return sum(1 for x in xs if x % 2 == 1)\n", "def count_even(xs):\n    return sum(1 for x in xs if x % 2 == 0)\n", ["count_even([1, 2, 4]) == 2"]),
("greet", "def greet(name):\n    return 'Hello, ' + name + '?'\n", "def greet(name):\n    return 'Hello, ' + name + '!'\n", ["greet('Ann') == 'Hello, Ann!'"]),
("factorial", "def factorial(n):\n    r = 0\n    for i in range(1, n + 1):\n        r *= i\n    return r\n", "def factorial(n):\n    r = 1\n    for i in range(1, n + 1):\n        r *= i\n    return r\n", ["factorial(4) == 24", "factorial(0) == 1"]),
("in_range", "def in_range(x, lo, hi):\n    return lo < x <= hi\n", "def in_range(x, lo, hi):\n    return lo <= x <= hi\n", ["in_range(0, 0, 5)", "in_range(5, 0, 5)", "not in_range(6, 0, 5)"]),
("double_all", "def double_all(xs):\n    return [x + 2 for x in xs]\n", "def double_all(xs):\n    return [x * 2 for x in xs]\n", ["double_all([1, 3]) == [2, 6]"]),
("first_n", "def first_n(xs, n):\n    return xs[:n - 1]\n", "def first_n(xs, n):\n    return xs[:n]\n", ["first_n([1, 2, 3], 2) == [1, 2]"]),
("is_empty", "def is_empty(s):\n    return len(s) == 1\n", "def is_empty(s):\n    return len(s) == 0\n", ["is_empty('')", "not is_empty('a')"]),
("contrast_ok", "def contrast_ok(ratio):\n    return ratio > 4.5\n", "def contrast_ok(ratio):\n    return ratio >= 4.5\n", ["contrast_ok(4.5)", "not contrast_ok(4.4)"]),
("px", "def px(n):\n    return str(n) + 'em'\n", "def px(n):\n    return str(n) + 'px'\n", ["px(4) == '4px'"]),
("countdown", "def countdown(n):\n    return list(range(n, 0, 1))\n", "def countdown(n):\n    return list(range(n, 0, -1))\n", ["countdown(3) == [3, 2, 1]"]),
("safe_div", "def safe_div(a, b):\n    if b == 1:\n        return None\n    return a / b\n", "def safe_div(a, b):\n    if b == 0:\n        return None\n    return a / b\n", ["safe_div(4, 0) is None", "safe_div(4, 1) == 4"]),
("join_words", "def join_words(ws):\n    return ''.join(ws)\n", "def join_words(ws):\n    return ' '.join(ws)\n", ["join_words(['a', 'b']) == 'a b'"]),
("min_val", "def min_val(a, b):\n    return a if a > b else b\n", "def min_val(a, b):\n    return a if a < b else b\n", ["min_val(1, 2) == 1", "min_val(5, 3) == 3"]),
("square", "def square(x):\n    return x * 2\n", "def square(x):\n    return x * x\n", ["square(3) == 9"]),
("odd_indices", "def odd_indices(xs):\n    return xs[0::2]\n", "def odd_indices(xs):\n    return xs[1::2]\n", ["odd_indices([0, 1, 2, 3]) == [1, 3]"]),
]

CONTRAST = [  # (fg, bg, expected ratio) -- canonical WCAG reference values
("#000000", "#ffffff", 21.0), ("#ffffff", "#ffffff", 1.0), ("#777777", "#ffffff", 4.48), ("#767676", "#ffffff", 4.54),
("#ff0000", "#ffffff", 4.0), ("#0000ff", "#ffffff", 8.59), ("#008000", "#ffffff", 5.14), ("#ffff00", "#000000", 19.56),
("#595959", "#ffffff", 7.0), ("#949494", "#ffffff", 3.03),
]


def run_tests(src: str, entry: str, tests: list[str]) -> bool:
    prog = src + f"\nf = {entry}\n" + "\n".join(f"assert {t}" for t in tests) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(prog)
    return subprocess.run([sys.executable, fh.name], capture_output=True, timeout=10).returncode == 0


def main(force: bool = False):
    OUT.mkdir(exist_ok=True)
    if (OUT / "code_problems.jsonl").exists() and not force:
        print("evalsets exist; frozen. Use --force to rebuild.")
        return
    probs = []
    for i, (name, sig, doc, body, tests) in enumerate(P):
        prompt = f'def {name}({sig}):\n    """{doc}"""\n'
        sol = prompt + "    " + body + "\n"
        assert run_tests(sol, name, tests), name
        probs.append({"id": f"xon-code-{i:03d}", "entry": name, "prompt": prompt, "solution": sol,
                      "tests": [t.replace("f(", f"{name}(") for t in tests], "license": "CC0-1.0"})
    assert len(probs) >= 60, len(probs)
    bugs = []
    for i, (name, buggy, fixed, tests) in enumerate(BUGS):
        assert run_tests(fixed, name, tests), name
        assert not run_tests(buggy, name, tests), name
        bugs.append({"id": f"xon-bug-{i:03d}", "entry": name, "buggy": buggy, "fixed": fixed, "tests": tests, "license": "CC0-1.0"})
    (OUT / "code_problems.jsonl").write_text("\n".join(json.dumps(p) for p in probs) + "\n")
    (OUT / "bugfix.jsonl").write_text("\n".join(json.dumps(b) for b in bugs) + "\n")
    (OUT / "contrast_cases.jsonl").write_text("\n".join(json.dumps({"fg": f, "bg": b, "ratio": r}) for f, b, r in CONTRAST) + "\n")
    # held-out synthetic UI (design fidelity + UI detection) and recognition: seeds far from training ranges
    (OUT / "ui_heldout.jsonl").write_text("\n".join(json.dumps({"seed": 9_000_000 + i}) for i in range(40)) + "\n")
    (OUT / "recognition_heldout.jsonl").write_text("\n".join(json.dumps({"seed": 7_000_000 + i}) for i in range(500)) + "\n")
    # perplexity: a frozen held-out slice of PSF-licensed stdlib modules + XON-written HTML/CSS
    import inspect, textwrap, colorsys, fnmatch, shlex, string, bisect
    ppl = []
    for mod in (colorsys, fnmatch, shlex, string, bisect):
        ppl.append({"id": f"ppl-{mod.__name__}", "text": inspect.getsource(mod), "license": "PSF-2.0", "lang": "python"})
    for i, seed in enumerate((8_000_001, 8_000_002, 8_000_003)):
        sys.path.insert(0, str(ROOT))
        from xon.datasets import synth_ui
        ppl.append({"id": f"ppl-html-{i}", "text": synth_ui.sample(seed)["html"], "license": "CC0-1.0", "lang": "html"})
    (OUT / "ppl_heldout.jsonl").write_text("\n".join(json.dumps(p) for p in ppl) + "\n")
    (OUT / "FROZEN").write_text("These eval sets are frozen. Crawling, training and the agent never write here.\n")
    print(f"wrote {len(probs)} code problems, {len(bugs)} bug-fix cases, {len(CONTRAST)} contrast cases")


if __name__ == "__main__":
    main("--force" in sys.argv)
