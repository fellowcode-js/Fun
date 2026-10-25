"""codegen: task -> implementation + tests with the warm-start code model; writes both files."""
SPEC = {"name": "codegen", "description": "Generate code + tests for a task (Python or C++) with the local pretrained coder; "
        "feedback = previous failure output; keep_tests = only regenerate the implementation (tests stay frozen).",
        "params": {"task": "str", "lang": "str?", "path": "str?", "feedback": "str?", "keep_tests": "bool?"}}


def examples_from_task(task: str, func: str | None) -> list[str]:
    """Example pairs the user wrote in the task ('Hello World' -> 'hello-world', f(2) == 4) become authoritative asserts."""
    import re
    out = []
    for m in re.finditer(r"""(?:\b(\w+)\(([^()]*)\)\s*(?:==|returns|->|=>)\s*([^,;]+?)(?=[,;]|\s+and\s|$))""", task):
        out.append(f"assert {m.group(1)}({m.group(2)}) == {m.group(3).strip()}")
    if func:
        for m in re.finditer(r"""(['"][^'"]*['"])\s*(?:->|=>|becomes|gives)\s*(['"][^'"]*['"])""", task):
            out.append(f"assert {func}({m.group(1)}) == {m.group(2)}")
    return out


def run(ctx, task: str, lang: str = "python", path: str = "", feedback: str = "", keep_tests: bool = False) -> dict:
    pt = ctx.pretrained()
    if pt is None:
        return {"ok": False, "error": "no pretrained coder (set [lm] init = \"pretrained\" and pip install xon[pretrained])"}
    r = pt.write_code(task, lang, feedback)
    ext = ".py" if lang == "python" else ".cpp"
    path = path or f"solution{ext}"
    code_p = ctx.path(path)
    code_p.parent.mkdir(parents=True, exist_ok=True)
    if lang == "python":
        import re
        code = r["code"]
        cut = re.search(r"\n(?:# ?Test|def test_|if __name__)", code)  # tests leaking into the implementation
        code_p.write_text((code[:cut.start()] if cut else code).rstrip() + "\n")
        mod = code_p.stem
        test_p = code_p.with_name(f"test_{mod}.py")
        from_task = examples_from_task(task, mod if re.search(rf"\bdef {mod}\b", code) else None)
        if keep_tests and test_p.exists():
            return {"ok": True, "path": str(code_p.relative_to(ctx.root)), "tests": str(test_p.relative_to(ctx.root)),
                    "lang": lang, "tests_frozen": True}
        body = r["tests"] or f"def test_imports():\n    import {mod}  # noqa: F401\n"
        body = re.sub(r"\n# Run the tests[\s\S]*$|\nif __name__[\s\S]*$", "\n", body)
        if f"from {mod} import" not in body and f"import {mod}" not in body:
            body = f"from {mod} import *  # noqa: F401,F403\n\n" + body
        if from_task:
            body += "\n\ndef test_examples_from_task():\n" + "".join(f"    {a}\n" for a in from_task)
        test_p.write_text(body.rstrip() + "\n")
        n_asserts = body.count("assert ")
        if n_asserts == 0:
            return {"ok": False, "error": "model produced no real assertions; refusing to call untested code verified",
                    "path": str(code_p.relative_to(ctx.root)), "tests": str(test_p.relative_to(ctx.root))}
        return {"ok": True, "path": str(code_p.relative_to(ctx.root)), "tests": str(test_p.relative_to(ctx.root)), "lang": lang,
                "asserts": n_asserts, "tests_source": "generated" + (f" + {len(from_task)} from task" if from_task else ""), "tests_frozen": False}
    else:
        code_p.write_text(r["code"].rstrip() + "\n")
        test_p = code_p.with_name(f"test_{code_p.stem}.cpp")
        main = r["tests"] if "int main" in r["tests"] else "int main() { return 0; }\n"
        test_p.write_text(f'#include "{code_p.name}"\n' + main.rstrip() + "\n")
    return {"ok": True, "path": str(code_p.relative_to(ctx.root)), "tests": str(test_p.relative_to(ctx.root)), "lang": lang}
