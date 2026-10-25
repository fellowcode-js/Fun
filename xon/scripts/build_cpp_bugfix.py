"""Blind C++ bug-fix set (XON-written, CC0). Written before running any repair on it."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from xon.agent.sandbox import run_cpp_tests  # noqa: E402
OUT = ROOT / "evalsets" / "cpp_bugfix_blind.jsonl"
B = [
("sum_to", "int sum_to(int n) {\n    int s = 0;\n    for (int i = 1; i < n; ++i) s += i;\n    return s;\n}\n", "<", "<=", ["sum_to(3) == 6", "sum_to(1) == 1"]),
("max2", "int max2(int a, int b) {\n    return a < b ? a : b;\n}\n", "a < b ? a : b", "a > b ? a : b", ["max2(1, 2) == 2", "max2(5, 3) == 5"]),
("is_odd", "bool is_odd(int n) {\n    return n % 2 == 0;\n}\n", "== 0", "!= 0", ["is_odd(3)", "!is_odd(4)"]),
("avg", "double avg(const vector<int>& v) {\n    double s = 0;\n    for (int x : v) s += x;\n    return s / (v.size() + 1);\n}\n", "(v.size() + 1)", "v.size()", ["avg({2, 4}) == 3.0"]),
("last", "int last(const vector<int>& v) {\n    return v[v.size() - 2];\n}\n", "- 2", "- 1", ["last({1, 2, 3}) == 3"]),
("count_pos", "int count_pos(const vector<int>& v) {\n    int c = 0;\n    for (int x : v) if (x >= 0) ++c;\n    return c;\n}\n", ">= 0", "> 0", ["count_pos({-1, 0, 2}) == 1"]),
("area", "int area(int w, int h) {\n    return w + h;\n}\n", "w + h", "w * h", ["area(3, 4) == 12"]),
("first_char", "char first_char(const string& s) {\n    return s[1];\n}\n", "s[1]", "s[0]", ["first_char(\"abc\") == 'a'"]),
]
if OUT.exists() and "--force" not in sys.argv:
    sys.exit("frozen")
rows = []
for i, (name, buggy, a, b, tests) in enumerate(B):
    fixed = buggy.replace(a, b, 1)
    assert run_cpp_tests(fixed, tests)["ok"] and not run_cpp_tests(buggy, tests)["ok"], name
    rows.append({"id": f"xon-cppbug-{i:03d}", "entry": name, "buggy": buggy, "fixed": fixed, "tests": tests, "lang": "cpp", "license": "CC0-1.0"})
OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(len(rows))
