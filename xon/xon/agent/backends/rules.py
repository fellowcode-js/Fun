"""Deterministic rules planner. Used when no external chat endpoint is configured.

It covers XON's core task shapes (build a small app, fix failing tests, design/critique a page, crawl,
train, status) as recipes: generators that yield tool calls and receive results. Honest scope: it does not
understand arbitrary tasks; it says so instead of pretending."""
from __future__ import annotations

import re


class RulesBackend:
    name = "rules"
    can_plan = False

    def classify(self, task: str) -> str:
        t = task.lower()
        if re.search(r"\b(fix|repair|debug)\b.*\b(test|bug|fail)", t) or re.search(r"failing tests?", t):
            return "fix_tests"
        if re.search(r"\b(build|create|make|scaffold)\b.*\b(app|tool|tracker|list)\b", t):
            return "build_app"
        if re.search(r"\bcritique|review the design|audit\b", t):
            return "critique"
        if re.search(r"\b(design|page|landing|layout|website|ui)\b", t):
            return "design_page"
        if re.search(r"\bpalette|colors?\b", t):
            return "palette"
        return "unknown"

    def plan_text(self, task: str) -> str:
        kind = self.classify(task)
        steps = {
            "build_app": ["Pick an app archetype and design tokens (accessible palette)", "Write app.js, index.html, tests",
                          "Run tests", "Screenshot in headless Chromium", "Critique the screenshot/DOM",
                          "Apply fixes, re-test, re-screenshot, re-critique", "Checkpoint with git; write summary + diff"],
            "fix_tests": ["Run the test suite", "Localize the fault (Ochiai over per-test line coverage)",
                          "Generate candidate patches on suspicious lines (mutation operators, LM-ranked if available)",
                          "Verify each candidate on failing tests, then the full suite", "Checkpoint; summary + diff"],
            "design_page": ["Parse the description into a layout spec", "Generate accessible HTML/CSS",
                            "Render + screenshot", "Critique (computed contrast, hierarchy, spacing, a11y)",
                            "Apply fixes and re-critique"],
            "critique": ["Render page / load screenshot", "Compute contrast, targets, labels, hierarchy, spacing", "Report"],
            "palette": ["Generate palette with computed contrast checks", "Generate type scale"],
            "unknown": ["The rules planner does not recognize this task. Set ANTHROPIC_API_KEY or XON_OPENAI_KEY "
                        "(+XON_OPENAI_BASE) to plan arbitrary tasks with an external model."],
        }[kind]
        return f"# Plan ({kind}, rules planner)\n\nTask: {task}\n\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)) + "\n"

    def recipe(self, task: str, ws: str = "."):
        kind = self.classify(task)
        return getattr(self, f"_{kind}")(task, ws)

    # ---- recipes: yield (tool, args) and receive results
    def _build_app(self, task, ws):
        from xon.agent import apps
        from xon.design import from_prompt, palette
        arch = apps.ARCHETYPES[apps.pick(task)]
        spec = from_prompt.parse(task)
        base = spec["palette"]["primary"]
        tokens = palette.generate(base, dark=spec["palette"]["dark"])["tokens"]
        title = re.search(r"(?:called|named)\s+['\"]?([\w ]{2,24}?)['\"]?(?:[,.]|$| with)", task)
        title = title.group(1).strip() if title else arch["title"]
        d = ws.rstrip("/")
        yield "write", {"path": f"{d}/index.html", "content": arch["html"](tokens, title)}
        for name, content in arch["files"].items():
            yield "write", {"path": f"{d}/{name}", "content": content}
        t1 = yield "test", {"target": d}
        shot1 = yield "_screenshot", {"path": f"{d}/index.html", "name": "before.png", "interact": True}
        c1 = yield "design", {"action": "critique", "path": f"{d}/index.html", "interact": True}
        fixed = yield "_improve", {"path": f"{d}/index.html", "report": c1}
        t2 = yield "test", {"target": d}
        shot2 = yield "_screenshot", {"path": f"{d}/index.html", "name": "after.png", "interact": True}
        c2 = yield "design", {"action": "critique", "path": f"{d}/index.html", "interact": True}
        yield "git", {"action": "checkpoint", "arg": f"build app: {task[:60]}"}
        return {"tests_before": t1.get("ok"), "tests_after": t2.get("ok"), "critique_before": c1.get("score"),
                "critique_after": c2.get("score"), "issues_before": len(c1.get("issues", [])),
                "issues_after": len(c2.get("issues", [])), "fixes": fixed.get("applied", []),
                "screenshots": [shot1.get("path"), shot2.get("path")]}

    def _fix_tests(self, task, ws):
        m = re.search(r"((?:tests?/)?[\w/]*test_[\w]+\.py|tests?/)", task)
        target = m.group(1) if m else ""
        t0 = yield "test", {"cmd": "", "target": target}
        if t0.get("ok"):
            return {"note": "tests already pass"}
        fx = yield "fix", {"tests": target or "tests"}
        t1 = yield "test", {"cmd": "", "target": target}
        if fx.get("ok") and t1.get("ok"):
            yield "git", {"action": "checkpoint", "arg": f"fix: {fx.get('file')}"}
        return {"fixed": bool(fx.get("ok") and t1.get("ok")), "file": fx.get("file"), "diff": fx.get("diff"),
                "tries": fx.get("tries"), "suspicious": fx.get("suspicious")}

    def _design_page(self, task, ws):
        d = ws.rstrip("/")
        r = yield "design", {"action": "from_prompt", "prompt": task, "out": f"{d}/index.html"}
        if not r.get("ok"):
            return {"error": r.get("error"), "refused": r.get("refused", False)}
        c1 = yield "design", {"action": "critique", "path": f"{d}/index.html"}
        fixed = yield "_improve", {"path": f"{d}/index.html", "report": c1}
        c2 = yield "design", {"action": "critique", "path": f"{d}/index.html"}
        shot = yield "_screenshot", {"path": f"{d}/index.html", "name": "page.png"}
        return {"critique_before": c1.get("score"), "critique_after": c2.get("score"), "fixes": fixed.get("applied", []),
                "screenshot": shot.get("path")}

    def _critique(self, task, ws):
        m = re.search(r"([\w./-]+\.(?:html|png|jpg))", task)
        path = m.group(1) if m else f"{ws}/index.html"
        r = yield "design", {"action": "critique", "path": path}
        return {"score": r.get("score"), "issues": r.get("issues")}

    def _palette(self, task, ws):
        m = re.search(r"#[0-9a-fA-F]{6}", task)
        r = yield "design", {"action": "palette", "base": m.group(0) if m else "#2f5fd0", "dark": "dark" in task.lower()}
        return r

    def _unknown(self, task, ws):
        return {"error": "rules planner cannot handle this task; configure an external backend"}
        yield  # pragma: no cover
