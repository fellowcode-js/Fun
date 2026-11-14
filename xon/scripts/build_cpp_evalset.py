"""Frozen C++ eval set (XON-written, CC0): signature + comment as prompt, hidden boolean tests, reference solution."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from xon.agent.sandbox import run_cpp_tests  # noqa: E402

OUT = ROOT / "evalsets" / "cpp_problems.jsonl"
P = [
("add", "int add(int a, int b)", "Return a + b.", "return a + b;", ["add(2, 3) == 5", "add(-1, 1) == 0"]),
("square", "long long square(long long x)", "Return x squared.", "return x * x;", ["square(4) == 16", "square(-3) == 9"]),
("is_even", "bool is_even(int n)", "True if n is even.", "return n % 2 == 0;", ["is_even(4)", "!is_even(7)", "is_even(0)"]),
("max_of", "int max_of(const vector<int>& v)", "Largest element of a non-empty vector.", "return *max_element(v.begin(), v.end());", ["max_of({1, 9, 3}) == 9", "max_of({-5, -2}) == -2"]),
("sum_vec", "long long sum_vec(const vector<int>& v)", "Sum of all elements.", "long long s = 0; for (int x : v) s += x; return s;", ["sum_vec({1, 2, 3}) == 6", "sum_vec({}) == 0"]),
("reverse_str", "string reverse_str(const string& s)", "Return s reversed.", "return string(s.rbegin(), s.rend());", ["reverse_str(\"abc\") == \"cba\"", "reverse_str(\"\") == \"\""]),
("count_char", "int count_char(const string& s, char c)", "Occurrences of c in s.", "return (int)count(s.begin(), s.end(), c);", ["count_char(\"banana\", 'a') == 3", "count_char(\"xyz\", 'a') == 0"]),
("factorial", "long long factorial(int n)", "n! for n >= 0.", "long long r = 1; for (int i = 2; i <= n; ++i) r *= i; return r;", ["factorial(0) == 1", "factorial(5) == 120", "factorial(10) == 3628800"]),
("fib", "long long fib(int n)", "n-th Fibonacci number, fib(0)=0, fib(1)=1.", "long long a = 0, b = 1; for (int i = 0; i < n; ++i) { long long t = a + b; a = b; b = t; } return a;", ["fib(0) == 0", "fib(1) == 1", "fib(10) == 55"]),
("is_palindrome", "bool is_palindrome(const string& s)", "True if s reads the same backwards.", "return equal(s.begin(), s.end(), s.rbegin());", ["is_palindrome(\"racecar\")", "!is_palindrome(\"ab\")", "is_palindrome(\"\")"]),
("gcd_of", "int gcd_of(int a, int b)", "Greatest common divisor (non-negative inputs).", "while (b) { int t = a % b; a = b; b = t; } return a;", ["gcd_of(12, 18) == 6", "gcd_of(7, 3) == 1", "gcd_of(0, 5) == 5"]),
("is_prime", "bool is_prime(int n)", "True if n is prime.", "if (n < 2) return false; for (int i = 2; (long long)i * i <= n; ++i) if (n % i == 0) return false; return true;", ["is_prime(2)", "is_prime(13)", "!is_prime(1)", "!is_prime(15)"]),
("count_vowels", "int count_vowels(const string& s)", "Count vowels (aeiou, case-insensitive).", "int c = 0; for (char ch : s) { char l = tolower(ch); if (string(\"aeiou\").find(l) != string::npos) ++c; } return c;", ["count_vowels(\"Hello\") == 2", "count_vowels(\"xyz\") == 0"]),
("dedupe", "vector<int> dedupe(const vector<int>& v)", "Remove duplicates keeping first occurrences in order.", "vector<int> out; set<int> seen; for (int x : v) if (seen.insert(x).second) out.push_back(x); return out;", ["dedupe({1, 2, 1, 3, 2}) == vector<int>({1, 2, 3})", "dedupe({}).empty()"]),
("filter_even", "vector<int> filter_even(const vector<int>& v)", "Even elements in order.", "vector<int> o; for (int x : v) if (x % 2 == 0) o.push_back(x); return o;", ["filter_even({1, 2, 3, 4}) == vector<int>({2, 4})"]),
("word_count", "int word_count(const string& s)", "Number of whitespace-separated words.", "istringstream in(s); string w; int n = 0; while (in >> w) ++n; return n;", ["word_count(\"a b  c\") == 3", "word_count(\"\") == 0"]),
("to_upper", "string to_upper(string s)", "Uppercase ASCII letters of s.", "for (char& c : s) c = toupper(c); return s;", ["to_upper(\"aBc1\") == \"ABC1\""]),
("clamp_int", "int clamp_int(int x, int lo, int hi)", "Clamp x into [lo, hi].", "return max(lo, min(hi, x));", ["clamp_int(5, 0, 10) == 5", "clamp_int(-1, 0, 10) == 0", "clamp_int(11, 0, 10) == 10"]),
("binary_str", "string binary_str(unsigned n)", "Binary representation without leading zeros ('0' for 0).", "if (n == 0) return \"0\"; string s; while (n) { s.push_back('0' + (n & 1)); n >>= 1; } reverse(s.begin(), s.end()); return s;", ["binary_str(5) == \"101\"", "binary_str(0) == \"0\""]),
("is_sorted_vec", "bool is_sorted_vec(const vector<int>& v)", "True if non-decreasing.", "return is_sorted(v.begin(), v.end());", ["is_sorted_vec({1, 2, 2, 3})", "!is_sorted_vec({2, 1})", "is_sorted_vec({})"]),
("second_largest", "int second_largest(vector<int> v)", "Second largest distinct value (at least two distinct values).", "sort(v.begin(), v.end()); v.erase(unique(v.begin(), v.end()), v.end()); return v[v.size() - 2];", ["second_largest({1, 3, 2}) == 2", "second_largest({5, 5, 4}) == 4"]),
("running_sum", "vector<long long> running_sum(const vector<int>& v)", "Prefix sums.", "vector<long long> o; long long t = 0; for (int x : v) { t += x; o.push_back(t); } return o;", ["running_sum({1, 2, 3}) == vector<long long>({1, 3, 6})"]),
("power_of_two", "bool power_of_two(long long n)", "True if n is a positive power of two.", "return n > 0 && (n & (n - 1)) == 0;", ["power_of_two(1)", "power_of_two(64)", "!power_of_two(0)", "!power_of_two(12)"]),
("char_freq", "map<char, int> char_freq(const string& s)", "Map each character to its count.", "map<char, int> m; for (char c : s) ++m[c]; return m;", ["char_freq(\"aab\") == map<char, int>({{'a', 2}, {'b', 1}})"]),
("transpose", "vector<vector<int>> transpose(const vector<vector<int>>& m)", "Transpose a non-empty rectangular matrix.", "vector<vector<int>> t(m[0].size(), vector<int>(m.size())); for (size_t i = 0; i < m.size(); ++i) for (size_t j = 0; j < m[0].size(); ++j) t[j][i] = m[i][j]; return t;", ["transpose({{1, 2}, {3, 4}}) == vector<vector<int>>({{1, 3}, {2, 4}})"]),
("pair_sum", "bool pair_sum(const vector<int>& v, int target)", "True if two different positions sum to target.", "unordered_set<int> s; for (int x : v) { if (s.count(target - x)) return true; s.insert(x); } return false;", ["pair_sum({1, 2, 3}, 5)", "!pair_sum({1, 2}, 5)"]),
("hex_color", "string hex_color(int r, int g, int b)", "Lowercase CSS hex color like #ff0000.", "char buf[8]; snprintf(buf, sizeof buf, \"#%02x%02x%02x\", r, g, b); return buf;", ["hex_color(255, 0, 0) == \"#ff0000\"", "hex_color(0, 128, 255) == \"#0080ff\""]),
("rotate_left", "vector<int> rotate_left(vector<int> v, int k)", "Rotate left by k positions.", "if (v.empty()) return v; k %= (int)v.size(); rotate(v.begin(), v.begin() + k, v.end()); return v;", ["rotate_left({1, 2, 3, 4}, 1) == vector<int>({2, 3, 4, 1})", "rotate_left({}, 3).empty()"]),
]
if OUT.exists() and "--force" not in sys.argv:
    sys.exit("frozen")
rows = []
for i, (name, sig, doc, body, tests) in enumerate(P):
    prompt = f"// {doc}\n{sig} {{\n"
    sol = prompt + "    " + body + "\n}\n"
    r = run_cpp_tests(sol, tests)
    assert r["ok"], (name, r)
    rows.append({"id": f"xon-cpp-{i:03d}", "entry": name, "prompt": prompt, "solution": sol, "tests": tests, "lang": "cpp", "license": "CC0-1.0"})
OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(len(rows))
