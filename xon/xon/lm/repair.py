"""`fix`: failing test + code -> patch. Search-based repair (mutation operators around suspicious lines),
candidates ranked by the XON LM when available, verified by actually running the tests."""
from __future__ import annotations

import ast
import re
from typing import Callable

ROR = ["<=", ">=", "==", "!=", "<", ">"]  # relational operator replacement: every op -> every other op
SWAPS = [(" + ", " - "), (" - ", " + "),
         (" * ", " + "), (" + ", " * "), (" * ", " / "), (" / ", " * "), (" and ", " or "), (" or ", " and "),
         ("min(", "max("), ("max(", "min("), ("''", "' '"), ("' '", "''"), ("[0::2]", "[1::2]"), ("[1::2]", "[0::2]"),
         ("% 2 == 1", "% 2 == 0"), ("% 2 == 0", "% 2 == 1"), ("True", "False"), ("False", "True")]


def _num_mutations(line: str) -> list[str]:
    out = []
    for m in re.finditer(r"(?<![\w.])(\d+)(?![\w.])", line):
        v = int(m.group(1))
        for nv in {v - 1, v + 1, 0, 1} - {v}:
            if nv >= 0:
                out.append(line[:m.start()] + str(nv) + line[m.end():])
    for m in re.finditer(r"\)\]|\)\s*:|\)$|\)\s*$", line):  # off-by-one on range()/len() ends
        k = m.start() + 1
        out.append(line[:m.start()] + " + 1" + line[m.start():])
        out.append(line[:m.start()] + " - 1" + line[m.start():])
        out.append(line[:k] + " + 1" + line[k:])
        out.append(line[:k] + " - 1" + line[k:])
    for m in re.finditer(r"range\(([^,()]+),\s*([^,()]+),\s*(-?\d+)\)", line):
        step = m.group(3)
        flipped = str(-int(step))
        out.append(line[:m.start(3)] + flipped + line[m.end(3):])
    return out


def _str_mutations(line: str) -> list[str]:
    out = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"", line):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        for a, b in (("?", "!"), ("!", "?"), ("em", "px"), ("px", "em"), (",", ""), (".", "!")):
            if a in s:
                out.append(line[:m.start()] + repr(s.replace(a, b)) + line[m.end():])
    return out


def mutants(code: str, focus: list[int] | None = None) -> list[str]:
    lines = code.split("\n")
    idxs = focus if focus else range(len(lines))
    seen, out = {code}, []
    for i in idxs:
        if i < 0 or i >= len(lines):
            continue
        line = lines[i]
        if line.strip().startswith(("def ", "#", '"""', "class ")):
            continue
        cands = []
        for m in re.finditer(r"(?<![<>=!])(<=|>=|==|!=|<|>)(?![<>=])", line):
            for op in ROR:
                if op != m.group(1):
                    cands.append(line[:m.start()] + op + line[m.end():])
        for a, b in SWAPS:
            if a in line:
                cands.append(line.replace(a, b, 1))
        cands += _num_mutations(line) + _str_mutations(line)
        for c in cands:
            new = "\n".join(lines[:i] + [c] + lines[i + 1:])
            if new in seen:
                continue
            seen.add(new)
            try:
                ast.parse(new)
            except SyntaxError:
                continue
            out.append(new)
    return out


def suspicious_lines(code: str, stderr: str) -> list[int]:
    """Lines named in the traceback first, then the body of the function under test."""
    lines = code.split("\n")
    hits = [int(m.group(1)) - 1 for m in re.finditer(r'line (\d+)', stderr) if int(m.group(1)) - 1 < len(lines)]
    rest = [i for i in range(len(lines)) if i not in hits]
    return hits + rest


def repair(code: str, run: Callable[[str], dict], scorer: Callable[[str], float] | None = None,
           max_tries: int = 300) -> dict:
    """run(code) -> {'ok': bool, 'stderr': str}. scorer(code) -> lower is better (e.g. LM loss)."""
    base = run(code)
    if base["ok"]:
        return {"ok": True, "patched": code, "tries": 0, "note": "tests already pass"}
    cands = mutants(code, suspicious_lines(code, base.get("stderr", "")))
    if scorer is not None:
        cands.sort(key=scorer)
    for n, c in enumerate(cands[:max_tries], 1):
        if run(c)["ok"]:
            return {"ok": True, "patched": c, "tries": n, "candidates": len(cands)}
    return {"ok": False, "patched": None, "tries": min(len(cands), max_tries), "candidates": len(cands)}


def unified_diff(a: str, b: str, name: str = "file.py") -> str:
    import difflib
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{name}", f"b/{name}"))
