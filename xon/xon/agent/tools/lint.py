"""Lint: Python (compile + pyflakes-style checks without dependencies) and C++ (-fsyntax-only -Wall -Wextra)."""
import ast
import subprocess
import tempfile
from pathlib import Path

SPEC = {"name": "lint", "description": "Lint a Python or C++ file: syntax, unused imports/variables, undefined names, "
        "mutable defaults, bare except; C++ compiler warnings.", "params": {"path": "str"}}


def _py(src: str) -> list[dict]:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [{"line": e.lineno, "kind": "syntax", "msg": e.msg}]
    out = []
    imported, used = {}, set()
    defined = set(dir(__builtins__)) | {"__file__", "__name__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                name = (a.asname or a.name).split(".")[0]
                imported[name] = node.lineno
                defined.add(name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
            if not isinstance(node, ast.ClassDef):
                for a in node.args.args + node.args.kwonlyargs + ([node.args.vararg] if node.args.vararg else []) + ([node.args.kwarg] if node.args.kwarg else []):
                    defined.add(a.arg)
                for d in node.args.defaults + node.args.kw_defaults:
                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                        out.append({"line": node.lineno, "kind": "mutable-default", "msg": f"mutable default argument in {node.name}()"})
        elif isinstance(node, ast.Name):
            (used.add(node.id) if isinstance(node.ctx, ast.Load) else defined.add(node.id))
        elif isinstance(node, ast.Attribute):
            pass
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                out.append({"line": node.lineno, "kind": "bare-except", "msg": "bare except: catches KeyboardInterrupt/SystemExit"})
            if node.name:
                defined.add(node.name)
        elif isinstance(node, (ast.comprehension,)):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    defined.add(n.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            defined.update(node.names)
    all_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            all_names |= {e.value for e in getattr(node.value, "elts", []) if isinstance(e, ast.Constant)}
    for name, line in imported.items():
        if name not in used and name not in all_names and not name.startswith("_"):
            out.append({"line": line, "kind": "unused-import", "msg": f"'{name}' imported but unused"})
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in defined:
            out.append({"line": node.lineno, "kind": "undefined-name", "msg": f"undefined name '{node.id}'"})
    return sorted(out, key=lambda d: d["line"] or 0)


def _cpp(path: Path) -> list[dict]:
    from xon.agent.sandbox import compiler
    cxx = compiler()
    if not cxx:
        return [{"line": None, "kind": "tool", "msg": "no C++ compiler"}]
    p = subprocess.run([cxx, "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-Wshadow", str(path)], capture_output=True, text=True, timeout=60)
    out = []
    for l in p.stderr.splitlines():
        parts = l.split(":", 4)
        if len(parts) >= 5 and parts[3].strip() in ("warning", "error"):
            out.append({"line": int(parts[1]) if parts[1].isdigit() else None, "kind": parts[3].strip(), "msg": parts[4].strip()})
    return out


def run(ctx, path: str) -> dict:
    p = ctx.path(path)
    if p.suffix in (".cpp", ".cc", ".cxx", ".hpp", ".h"):
        issues = _cpp(p)
    else:
        issues = _py(p.read_text())
    return {"ok": not any(i["kind"] in ("syntax", "error", "undefined-name") for i in issues), "issues": issues[:100], "count": len(issues)}
