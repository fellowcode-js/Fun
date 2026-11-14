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
        if re.search(r"\b(make|create|spawn|hire|build|set up|give me|add)\b.{0,24}\b(sub-?agents?|helpers?|assistants?|specialists?|workers?)\b", t):
            return "spawn_subagent"
        if re.match(r"\s*(ask|tell|have|let|get)\s+[\w-]+\s+(to\s+)?\w", t) and re.search(r"\b(ask|tell|have|let|get)\s+([\w-]+)", t) \
                and not re.match(r"\s*(let|get)\s+(me|us|it|the|a)\b", t):
            return "delegate"
        if re.search(r"\b(fix|repair|debug)\b.*\b(test|bug|fail)", t) or re.search(r"failing tests?", t):
            return "fix_tests"
        if re.search(r"\b(build|create|make|scaffold)\b.*\b(todo|to-do|checklist|task list)\b", t):
            return "build_app"
        if re.search(r"\b(write|implement|code|create|make)\b", t) and \
                re.search(r"\b(function|class|script|program|algorithm|parser|cli|module|python)\b|c\+\+|\bcpp\b", t):
            return "write_code"
        if re.search(r"\b(build|create|make|scaffold)\b.*\b(app|tool|tracker|list)\b", t):
            return "build_app"
        if re.search(r"\banimat\w*|\b(gif|walk cycle|keyframes?|looping)\b|\b(bouncing|spinning|waving|pulsing|floating|walking|jumping) \w+", t) \
                or re.search(r"\b(ball|star|heart|stick ?figure|dots|spinner)\b.*\b(bounc|spin|wav|puls|float|walk|jump|orbit|shak)\w*", t):
            return "animate"
        if re.search(r"\bcritique|review the design|audit\b", t):
            return "critique"
        if re.search(r"\b(design|page|landing|layout|website|ui)\b", t):
            return "design_page"
        if re.search(r"\bpalette|colors?\b", t):
            return "palette"
        return "unknown"

    def plan_text(self, task: str, kind: str | None = None) -> str:
        kind = kind or self.classify(task)
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
            "write_code": ["Generate implementation + tests with the local pretrained coder", "Compile/run the tests in the sandbox",
                           "If they fail: note the failure in the scratchpad, feed the error back, regenerate (up to 3 attempts)",
                           "Still failing: localize + mutation repair against the generated tests", "Lint, checkpoint, summary"],
            "animate": ["Parse the description (subject, motion, colour, speed, count)", "Render the motion to SVG/CSS + GIF",
                        "Self-check: it moves, loops cleanly, stays on stage", "Screenshot the page", "Checkpoint"],
            "spawn_subagent": ["Work out the specialty from the request", "Pick the XON tools that specialty needs (nothing else)",
                               "Create the sub-agent with its own folder", "If a first job was given, hand it over"],
            "delegate": ["Find the named sub-agent", "Hand it the job", "Report what it made"],
            "unknown": ["XON's local planner does not recognize this task yet. It handles: build an app, write code, fix "
                        "failing tests, design a page, make an animation, critique, palette, and creating / asking sub-agents."],
        }[kind]
        return f"# Plan ({kind}, rules planner)\n\nTask: {task}\n\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)) + "\n"

    def route(self, task: str, pretrained=None) -> str:
        """Rules first; for tasks they don't recognize, let the local pretrained model pick one recipe by name."""
        kind = self.classify(task)
        if kind != "unknown" or pretrained is None:
            return kind
        pretrained = pretrained() if callable(pretrained) else pretrained  # only load the model when it is needed
        if pretrained is None:
            return kind
        choices = ["build_app", "write_code", "fix_tests", "design_page", "animate", "critique", "palette"]
        reply = pretrained.chat([{"role": "user", "content": f"Task: {task}\nWhich ONE of these handles it best: {', '.join(choices)}, "
                                  "or none? Answer with just the name."}], max_new=8).strip().lower()
        return next((c for c in choices if c in reply), "unknown")

    def recipe(self, task: str, ws: str = ".", kind: str | None = None):
        kind = kind or self.classify(task)
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
        """Best-of-two + iterate: spec engine vs pretrained-model HTML, critique both, keep the better one, then
        critique -> fix rounds until the score stops improving or reaches 95."""
        d = ws.rstrip("/")
        r = yield "design", {"action": "from_prompt", "prompt": task, "out": f"{d}/index.html"}
        if not r.get("ok"):
            return {"error": r.get("error"), "refused": r.get("refused", False)}
        c_spec = yield "design", {"action": "critique", "path": f"{d}/index.html"}
        alt = yield "design", {"action": "from_prompt", "prompt": task, "out": f"{d}/alt.html", "engine": "pretrained"}
        chosen, c1 = "spec", c_spec
        if alt.get("ok"):
            c_alt = yield "design", {"action": "critique", "path": f"{d}/alt.html"}
            yield "think", {"note": f"spec engine scored {c_spec.get('score')}, pretrained engine scored {c_alt.get('score')}"}
            if (c_alt.get("score") or 0) > (c_spec.get("score") or 0) + 5 and c_alt.get("contrast_failed", 1) == 0:
                chosen, c1 = "pretrained", c_alt
                yield "shell", {"cmd": f"cp {d}/alt.html {d}/index.html"}
        scores, fixes = [c1.get("score")], []
        cur = c1
        for _ in range(3):
            if (cur.get("score") or 0) >= 95 or not cur.get("issues"):
                break
            fx = yield "_improve", {"path": f"{d}/index.html", "report": cur}
            nxt = yield "design", {"action": "critique", "path": f"{d}/index.html"}
            yield "think", {"note": f"round {len(scores)}: {cur.get('score')} -> {nxt.get('score')} via {fx.get('applied')}"}
            if (nxt.get("score") or 0) <= (cur.get("score") or 0):
                break
            fixes += fx.get("applied", [])
            scores.append(nxt.get("score"))
            cur = nxt
        shot = yield "_screenshot", {"path": f"{d}/index.html", "name": "page.png"}
        return {"engine": chosen, "critique_rounds": scores, "critique_before": scores[0], "critique_after": scores[-1],
                "fixes": fixes, "screenshot": shot.get("path")}

    def _write_code(self, task, ws):
        lang = "cpp" if re.search(r"c\+\+|\bcpp\b", task.lower()) else "python"
        d = ws.rstrip("/")
        name = re.sub(r"[^a-z0-9]+", "_", (re.search(r"(?:called|named)\s+([\w]+)", task) or [None, "solution"])[1].lower())
        path = f"{d}/{name}.{'py' if lang == 'python' else 'cpp'}"
        feedback, attempts, tests_source, g = "", [], "none", {}
        for attempt in range(1, 4):
            g = yield "codegen", {"task": task, "lang": lang, "path": path, "feedback": feedback, "keep_tests": attempt > 1}
            if g.get("tests_source"):
                tests_source = g["tests_source"]
            if not g.get("ok"):
                if attempt < 3 and "no real assertions" in str(g.get("error")):
                    feedback = "Your tests had no assert statements. Write real pytest asserts."
                    attempts.append(False)
                    continue
                return {"error": g.get("error")}
            if lang == "python":
                t = yield "test", {"target": g["tests"]}
                out = t.get("output", "")
            else:
                src = f'#include <bits/stdc++.h>\nusing namespace std;\n#include "{name}.cpp"\n'
                t = yield "cpp_build", {"path": g["tests"]}
                out = t.get("stderr", "") + t.get("stdout", "")
            attempts.append(bool(t.get("ok")))
            if t.get("ok"):
                break
            yield "think", {"note": f"attempt {attempt} failed; last error lines: {out.strip().splitlines()[-1:] if out.strip() else 'none'}"}
            feedback = out
        repaired = None
        if not attempts[-1] and lang == "python":
            fx = yield "fix", {"tests": g["tests"]}
            repaired = bool(fx.get("ok"))
        lint = yield "lint", {"path": path}
        ok = attempts[-1] or bool(repaired)
        if ok:
            yield "git", {"action": "checkpoint", "arg": f"write code: {task[:60]}"}
        return {"ok": ok, "lang": lang, "file": path, "tests": g.get("tests"), "tests_source": tests_source,
                "warning": "verified only against model-written tests; review them" if "from task" not in tests_source else None,
                "attempts": len(attempts),
                "passed_on_attempt": attempts.index(True) + 1 if True in attempts else None, "repaired_by_fix": repaired,
                "lint_issues": lint.get("count")}

    def _animate(self, task, ws):
        d = ws.rstrip("/")
        words = [w for w in re.findall(r"[a-z]+", task.lower()) if w not in ("a", "an", "the", "make", "me", "animation", "animate",
                                                                               "of", "with", "and", "create", "please", "on", "in")]
        name = "-".join(words[:3]) or "animation"
        r = yield "animate", {"prompt": task, "out": f"{d}/{name}"}
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error"), "refused": r.get("refused", False)}
        qc = r.get("check", {})
        yield "think", {"note": f"subject {r['spec']['subject']}, motions {r['spec']['motions']}, {qc.get('frames')} frames, "
                                f"moves={qc.get('moves')}, loop seam {qc.get('loop_seam')}, touches edge={qc.get('touches_edge')}"}
        shot = yield "_screenshot", {"path": r["html"], "name": f"{name}.png"}
        yield "git", {"action": "checkpoint", "arg": f"animation: {task[:60]}"}
        return {"ok": bool(qc.get("moves")), "html": r["html"], "gif": r["gif"], "subject": r["spec"]["subject"],
                "motions": r["spec"]["motions"], "count": r["spec"]["count"], "check": qc, "screenshot": shot.get("path")}

    def _spawn_subagent(self, task, ws):
        first = re.search(r"\b(?:,?\s*and (?:then )?(?:have|ask|tell|get|let) (?:it|them|him|her)(?: to)?|,?\s*then|and make it)\s+(.+)$", task, re.I)
        spec_task = task[:first.start()] if first else task
        r = yield "subagent", {"action": "create", "task": spec_task}
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        a = r["agent"]
        out = {"ok": True, "created": a["id"], "name": a["name"], "role": a["role"], "tools": a["tools"],
               "hint": f"give it work: xon subagent talk {a['id']} \"...\"  (or tell XON: ask {a['name']} to ...)"}
        if first:
            job = yield "subagent", {"action": "run", "id": a["id"], "message": first.group(1)}
            out["first_job"] = {"reply": job.get("reply"), "files": job.get("files")}
        return out

    def _delegate(self, task, ws):
        m = re.search(r"\b(?:ask|tell|have|let|get)\s+([\w-]+)\s+(?:to\s+)?(.+)$", task, re.I)
        if not m:
            return {"ok": False, "error": "who should do it? e.g. 'ask Pixel to make a spinning star'"}
        r = yield "subagent", {"action": "run", "id": m.group(1), "message": m.group(2)}
        return {"ok": r.get("ok", False), "agent": m.group(1), "reply": r.get("reply"), "files": r.get("files"), "error": r.get("error")}

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
