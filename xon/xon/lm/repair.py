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


def mutants(code: str, focus: list[int] | None = None, lang: str = "python") -> list[str]:
    lines = code.split("\n")
    idxs = focus if focus else range(len(lines))
    seen, out = {code}, []
    for i in idxs:
        if i < 0 or i >= len(lines):
            continue
        line = lines[i]
        if line.strip().startswith(("def ", "#", '"""', "class ", "//", "#include")):
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
            if lang == "python":
                try:
                    ast.parse(new)
                except SyntaxError:
                    continue
            out.append(new)
    return out


def specializes(orig: str, cand: str) -> int:
    """1 if the candidate turns an inequality into ==/!= (patches like `total == 50` that fit the tests but
    overfit them); such candidates are tried after boundary shifts like `>=` or `> 49`."""
    import difflib
    for a, b in zip(orig.splitlines(), cand.splitlines()):
        if a != b:
            ineq = re.search(r"[<>]=?", a) and not re.search(r"[<>]=?", b)
            return 1 if ineq and re.search(r"[=!]=", b) else 0
    _ = difflib
    return 0


def rank(orig: str, cands: list[str], scorer=None) -> list[str]:
    """Order: non-specializing first; LM score (if any) breaks ties inside each group."""
    return sorted(cands, key=lambda c: (specializes(orig, c), scorer(c) if scorer else 0))


def suspicious_lines(code: str, stderr: str) -> list[int]:
    """Lines named in the traceback first, then the body of the function under test."""
    lines = code.split("\n")
    hits = [int(m.group(1)) - 1 for m in re.finditer(r'line (\d+)', stderr) if int(m.group(1)) - 1 < len(lines)]
    rest = [i for i in range(len(lines)) if i not in hits]
    return hits + rest


def repair(code: str, run: Callable[[str], dict], scorer: Callable[[str], float] | None = None,
           max_tries: int = 300, lang: str = "python", rewriter: Callable[[str, str], list[str]] | None = None) -> dict:
    """run(code) -> {'ok': bool, 'stderr': str}. scorer(code) -> lower is better (e.g. LM loss).
    Stage 1: mutation search around suspicious lines. Stage 2 (if given): LLM rewrites from the failure output.
    Every candidate is verified by `run`; nothing unverified is returned."""
    base = run(code)
    if base["ok"]:
        return {"ok": True, "patched": code, "tries": 0, "note": "tests already pass"}
    cands = rank(code, mutants(code, suspicious_lines(code, base.get("stderr", "")), lang=lang), scorer)
    n = 0
    for n, c in enumerate(cands[:max_tries], 1):
        if run(c)["ok"]:
            return {"ok": True, "patched": c, "tries": n, "candidates": len(cands), "stage": "mutation"}
    if rewriter is not None:
        for c in rewriter(code, base.get("stderr", "") + base.get("stdout", "")):
            n += 1
            if c.strip() and run(c)["ok"]:
                return {"ok": True, "patched": c, "tries": n, "candidates": len(cands), "stage": "llm-rewrite"}
    return {"ok": False, "patched": None, "tries": n, "candidates": len(cands)}


def unified_diff(a: str, b: str, name: str = "file.py") -> str:
    import difflib
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{name}", f"b/{name}"))
