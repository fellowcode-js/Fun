"""Sub-agents: XON spawns its own helpers for a task and gives each one only the tools it needs.

Two kinds, both created from one line of text (by you, or by XON itself when you ask it for a helper):

  specialists  work for you inside XON, each in its own folder, by running XON's own agent loop restricted to
               the specialty's tools: animator (animations), designer (pages / app screens), coder (Python, C++),
               tester (fix failing tests), app builder, and a general helper for anything else.
                 sa = create("a helper that makes animations")      ->  "Pixel", tools: animate, read, write, ...
                 sa.talk("a red ball bouncing, slow")               ->  Pixel/anim/red-ball-bouncing.html + .gif
  characters   live in a game and act through that game's tools (shopkeeper, blacksmith, innkeeper, guard, quest
               giver, any NPC): create("be a shopkeeper in my game named Greta", toolkit="demo" | "game_tools.json")

Everything runs on this machine: no API keys, no cloud models. The thinking is XON's rules planner plus its local
models; a character's line can optionally be re-voiced by the local model (brain="local").
A sub-agent can never call a tool it was not granted (Permissions / Toolkit.call refuse it).
Specs, memory and work folders live in <root>/.xon/subagents/ and <root>/subagents/<id>/.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from pathlib import Path

from xon.game import Toolkit, ToolDenied, load_toolkit

# specialists: kind = the XON recipe they run; tools = XON agent tools they may use
SPECIALISTS: dict[str, dict] = {
    "animator": {
        "keywords": ["animation", "animations", "animate", "animator", "animating", "gif", "gifs", "motion", "cartoon",
                     "loop", "loops", "keyframe", "keyframes", "sprite animation", "walk cycle"],
        "kind": "animate", "tools": ["animate", "read", "write", "think", "view_image", "git"],
        "names": ["Pixel", "Flip", "Loop", "Cel"],
        "persona": "an animator who turns descriptions into looping animations (web page + GIF)",
    },
    "designer": {
        "keywords": ["design", "designer", "designs", "page", "pages", "landing", "website", "ui", "screen", "screens",
                     "layout", "layouts", "mockup", "interface"],
        "kind": "design_page", "tools": ["design", "read", "write", "edit", "think", "shell", "view_image", "git"],
        "names": ["Swatch", "Grid", "Kern"],
        "persona": "a UI designer who builds accessible pages and checks contrast with math",
    },
    "coder": {
        "keywords": ["coder", "programmer", "code", "coding", "developer", "python", "c++", "cpp", "script", "scripts",
                     "function", "functions", "algorithm", "algorithms", "program", "programs"],
        "kind": "write_code", "tools": ["codegen", "test", "cpp_build", "python_run", "fix", "lint", "read", "write", "edit",
                                        "think", "git"],
        "names": ["Byte", "Ada", "Lint"],
        "persona": "a careful coder who writes code with tests and runs them before saying it works",
    },
    "tester": {
        "keywords": ["tester", "debugger", "debug", "bug", "bugs", "failing", "tests", "qa", "fixer"],
        "kind": "fix_tests", "tools": ["test", "fix", "read", "grep", "think", "git"],
        "names": ["Probe", "Patch"],
        "persona": "a bug hunter who localizes failing tests and verifies every fix",
    },
    "builder": {
        "keywords": ["app", "apps", "builder", "todo", "tracker", "tool", "tools"],
        "kind": "build_app", "tools": ["write", "read", "edit", "test", "design", "think", "git"],
        "names": ["Forge", "Brick"],
        "persona": "an app builder who scaffolds small web apps with tests",
    },
    "helper": {
        "keywords": [],
        "kind": None, "tools": ["read", "write", "edit", "glob", "grep", "think", "python_run"],
        "names": ["Wren", "Tobin", "Lark"],
        "persona": "a general helper",
    },
}

# characters: act inside a game through its toolkit
ROLES: dict[str, dict] = {
    "shopkeeper": {
        "keywords": ["shopkeeper", "shop", "merchant", "vendor", "store", "trader", "seller", "market", "general store"],
        "tools": ["shop_inventory", "check_price", "player_wallet", "sell_to_player", "buy_from_player", "shop_restock"],
        "tool_words": ["shop", "price", "wallet", "sell", "buy", "inventory", "stock", "trade"],
        "names": ["Greta", "Odo", "Marla", "Pim", "Hollis", "Tamsin", "Bram"],
        "persona": "a friendly but shrewd shopkeeper who knows every item and price on the shelves",
        "rules": ["Only quote prices and items that come from the shop's tools.", "Never sell below the floor price.",
                  "Haggle a little: accept offers of at least 85% of list price, otherwise counter at 92%."],
    },
    "blacksmith": {
        "keywords": ["blacksmith", "smith", "forge master", "armorer", "weaponsmith"],
        "tools": ["shop_inventory", "check_price", "player_wallet", "sell_to_player", "buy_from_player", "shop_restock"],
        "tool_words": ["shop", "price", "wallet", "sell", "buy", "repair", "forge"],
        "names": ["Durgan", "Helka", "Ivo"],
        "persona": "a gruff blacksmith who respects good steel and fair coin",
        "rules": ["Only quote prices and items that come from the shop's tools.", "Never sell below the floor price."],
    },
    "innkeeper": {
        "keywords": ["innkeeper", "inn", "tavern", "barkeep", "bartender"],
        "tools": ["shop_inventory", "check_price", "player_wallet", "sell_to_player", "give_quest"],
        "tool_words": ["room", "drink", "food", "shop", "price", "sell", "quest", "rumor"],
        "names": ["Mabel", "Corwin", "Nessa"],
        "persona": "a warm innkeeper who hears every rumour in town",
        "rules": ["Only quote prices that come from the tools."],
    },
    "guard": {
        "keywords": ["guard", "gate", "watchman", "sentry", "patrol", "soldier"],
        "tools": ["open_gate", "close_gate", "player_wallet"],
        "tool_words": ["gate", "door", "arrest", "patrol", "alarm"],
        "names": ["Captain Roderick", "Sera", "Volk"],
        "persona": "a stern town guard who opens the gate only for a good reason",
        "rules": ["Open the gate only when the player gives a reason.", "Close it again when asked or at night."],
    },
    "questgiver": {
        "keywords": ["quest", "mission", "bounty", "elder", "questgiver", "quest giver", "mayor"],
        "tools": ["give_quest", "player_wallet"],
        "tool_words": ["quest", "mission", "reward", "bounty"],
        "names": ["Elder Wynn", "Mayor Pell", "Old Ida"],
        "persona": "a village elder who hands out quests for gold",
        "rules": ["Give each player at most one open quest at a time."],
    },
    "npc": {
        "keywords": ["npc", "villager", "townsperson", "character"],
        "tools": [],
        "tool_words": [],
        "names": ["Wren", "Tobin", "Lark"],
        "persona": "a townsperson",
        "rules": ["Stay in character."],
    },
}
GAME_WORDS = r"\b(game|npc|player|players|rpg|village|town|tavern|quest|in-game|shopkeeper|merchant|guard|blacksmith|innkeeper)\b"


def _score(task: str, words: list[str]) -> int:
    t = task.lower()
    return sum(2 if re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", t) else 0 for k in words)


def pick_role(task: str, toolkit=None) -> str:
    """Character role if the task is about a game (or a game toolkit was given), otherwise a specialist."""
    game = toolkit not in (None, "", "code") or re.search(GAME_WORDS, task.lower())
    best, score = None, 0
    for role, r in ROLES.items():
        sc = _score(task, r["keywords"]) + (1 if game else -1)
        if sc > score:
            best, score = role, sc
    if best and (game or score >= 2) and best != "npc":
        return best
    sbest, sscore = "helper", 0
    for role, r in SPECIALISTS.items():
        sc = _score(task, r["keywords"])
        if sc > sscore:
            sbest, sscore = role, sc
    if game and sscore == 0:
        return best or "npc"
    return sbest


def pick_name(task: str, role: str) -> str:
    m = re.search(r"\b(?:named|called|name is|name him|name her|name them|name it)\s+([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?)", task)
    if m:
        return m.group(1)
    names = (ROLES.get(role) or SPECIALISTS[role])["names"]
    return names[int(hashlib.sha1(task.encode()).hexdigest(), 16) % len(names)]


def grant_tools(role: str, tk: Toolkit, allow: list[str] | None = None, deny: list[str] | None = None) -> list[str]:
    r = ROLES[role]
    names = list(tk.tools)
    got = [n for n in names if n in r["tools"]]
    if not got:  # a custom game toolkit: match by words in the tool's name/description
        for n, t in tk.tools.items():
            text = f"{n} {t.description}".lower()
            if any(w in text for w in r["tool_words"]):
                got.append(n)
    got += [n for n in (allow or []) if n in names and n not in got]
    return [n for n in got if n not in (deny or [])]


def grant_xon_tools(role: str, task: str, allow: list[str] | None = None, deny: list[str] | None = None) -> list[str]:
    """Specialty tools, plus any XON tool whose name the task mentions (e.g. 'a helper that can use sqlite')."""
    from xon.agent.tools import MODULES
    got = list(SPECIALISTS[role]["tools"])
    tl = task.lower()
    for n in MODULES:
        if n not in got and n not in ("subagent", "shell") and re.search(rf"\b{n}\b", tl):
            got.append(n)
    got += [n for n in (allow or []) if n in MODULES and n not in got]
    return [n for n in got if n not in (deny or []) and n != "subagent"]  # sub-agents don't spawn sub-agents


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "agent"


def _store(root: Path) -> Path:
    d = Path(root) / ".xon" / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(task: str, toolkit: str | dict | None = None, *, name: str | None = None, role: str | None = None,
           allow: list[str] | None = None, deny: list[str] | None = None, brain: str = "rules",
           root: Path | str = ".") -> "SubAgent":
    root = Path(root)
    role = role if role in ROLES or role in SPECIALISTS else pick_role(task, toolkit)
    name = name or pick_name(task, role)
    spec = {"id": _slug(name), "name": name, "role": role, "task": task, "brain": "local" if brain == "local" else "rules",
            "created": time.time()}
    if role in SPECIALISTS:
        sp = SPECIALISTS[role]
        spec.update({"kind": "specialist", "recipe": sp["kind"], "persona": f"{name}, {sp['persona']}",
                     "tools": grant_xon_tools(role, task, allow, deny), "toolkit": "xon", "game": "XON",
                     "workdir": f"subagents/{_slug(name)}"})
        tk = None
    else:
        toolkit = toolkit or "demo"
        tk = load_toolkit(toolkit, root)
        spec.update({"kind": "character", "persona": f"{name}, {ROLES[role]['persona']}", "rules": ROLES[role]["rules"],
                     "tools": grant_tools(role, tk, allow, deny), "toolkit": toolkit if isinstance(toolkit, str) else "inline",
                     "game": tk.game})
        if not isinstance(toolkit, str) and toolkit is not None:
            (_store(root) / f"{spec['id']}.toolkit.json").write_text(json.dumps(toolkit, indent=1))
            spec["toolkit"] = str(_store(root) / f"{spec['id']}.toolkit.json")
    (_store(root) / f"{spec['id']}.json").write_text(json.dumps(spec, indent=1))
    return SubAgent(spec, root, tk)


def load(agent_id: str, root: Path | str = ".") -> "SubAgent":
    root = Path(root)
    p = _store(root) / f"{_slug(agent_id)}.json"
    if not p.exists():
        raise KeyError(f"no sub-agent '{agent_id}' (see `xon subagent list`)")
    spec = json.loads(p.read_text())
    tk = None if spec.get("kind") == "specialist" else load_toolkit(spec["toolkit"], root)
    return SubAgent(spec, root, tk)


def list_all(root: Path | str = ".") -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_store(Path(root)).glob("*.json"))
            if not p.name.endswith((".memory.json", ".toolkit.json"))]


def remove(agent_id: str, root: Path | str = ".") -> bool:
    d = _store(Path(root))
    hit = False
    for suffix in (".json", ".memory.json", ".toolkit.json"):
        p = d / f"{_slug(agent_id)}{suffix}"
        if p.exists():
            p.unlink()
            hit = True
    return hit


# ------------------------------------------------------------------------------------------------ the agent

class SubAgent:
    def __init__(self, spec: dict, root: Path, toolkit: Toolkit | None):
        self.spec, self.root, self.tk = spec, Path(root), toolkit
        self._mem_path = _store(self.root) / f"{spec['id']}.memory.json"
        self.memory: dict = json.loads(self._mem_path.read_text()) if self._mem_path.exists() else {}

    @property
    def name(self) -> str:
        return self.spec["name"]

    @property
    def is_specialist(self) -> bool:
        return self.spec.get("kind") == "specialist"

    def call(self, tool: str, args: dict, actions: list) -> dict:
        try:
            res = self.tk.call(tool, args, self.spec["tools"])
        except ToolDenied as e:
            res = {"ok": False, "denied": True, "error": str(e)}
        actions.append({"tool": tool, "args": args, "result": res})
        return res

    def _remember(self, player: str, msg: str, reply: str, actions: list):
        h = self.memory.setdefault(player, {"turns": [], "pending": None})
        h["turns"] = (h["turns"] + [{"player": msg, "npc": reply, "tools": [a["tool"] for a in actions]}])[-20:]
        self._mem_path.write_text(json.dumps(self.memory, indent=1))

    def brain(self) -> str:
        return self.spec.get("brain", "rules")

    def talk(self, message: str, player: str = "player", brain: str | None = None, voice=None) -> dict:
        """A job (specialist) or a line from a player (character) -> {reply, actions, files, brain}."""
        t0 = time.time()
        b = brain or self.brain()
        if b not in ("rules", "local"):
            b = "rules"
        actions: list[dict] = []
        files: list[str] = []
        ok = True
        if self.is_specialist:
            reply, files, ok = self._work(message, actions)
        else:
            reply = self._rules(message, player, actions)
            if b == "local":
                reply = self._voice(reply, message, voice) or reply
        self._remember(player, message, reply, actions)
        return {"agent": self.spec["id"], "name": self.name, "ok": ok, "reply": reply, "actions": actions, "files": files,
                "brain": b, "seconds": round(time.time() - t0, 2)}

    # ---- specialists: XON's own agent loop, in the sub-agent's folder, limited to its tools
    def _work(self, message: str, actions: list) -> tuple[str, list[str], bool]:
        from xon import config
        from xon.agent.backends.rules import RulesBackend
        from xon.agent.loop import Agent
        from xon.agent.permissions import Permissions
        work = self.root / self.spec["workdir"]
        work.mkdir(parents=True, exist_ok=True)
        block = re.search(r"```(\w*)\n(.*?)```", message, re.S)
        if block and "python_run" in self.spec["tools"] and block.group(1).lower() in ("", "py", "python"):
            from xon.agent.tools import Context, registry
            r = registry()["python_run"].run(Context(work, config.load(self.root)), code=block.group(2))
            actions.append({"tool": "python_run", "args": {"code": block.group(2)[:200]}, "result": {"ok": r.get("ok")}})
            out = (r.get("stdout") or "") + (r.get("stderr") or "")
            return (f"{'It ran fine' if r.get('ok') else 'It failed'}. Output:\n```\n{out.strip()[-1500:] or '(no output)'}\n```",
                    [], bool(r.get("ok")))
        cfg = config.load(self.root)
        if not (self.root / "xon.toml").exists():  # a workspace inside XON: reuse XON's models and checkpoints
            home = config.load()
            for k in ("checkpoints", "evalsets"):
                cfg["paths"][k] = str(config.path(home, k))
            cfg["lm"] = home["lm"]
        ag = Agent(work, cfg, mode="auto-edit", backend="rules", assume_yes=True, max_steps=40)
        ag.perms = Permissions("auto-edit", allowlist=self.spec["tools"], assume_yes=True)
        kind = RulesBackend().classify(message)
        recipe = self.spec.get("recipe")
        allowed = {recipe} if recipe else set()
        allowed |= {"critique", "palette"} if recipe in ("design_page", "build_app") else set()
        if recipe is None:  # general helper: whatever the planner recognizes, minus spawning more agents
            kind = kind if kind not in ("spawn_subagent", "delegate") else "unknown"
        elif kind not in allowed:
            kind = recipe  # a specialist reads every job as its specialty
        before = {p for p in work.rglob("*") if p.is_file()}
        summary = ag.run(message, ".", kind=kind)
        art = work / summary.get("artifacts", "")
        if (art / "log.jsonl").exists():
            for line in (art / "log.jsonl").read_text().splitlines():
                st = json.loads(line)
                actions.append({"tool": st["tool"], "args": {k: v for k, v in (st.get("args") or {}).items() if k != "content"},
                                "result": {"ok": st.get("ok"), "error": st.get("error"),
                                           "denied": "not in xon.toml agent.tool_allowlist" in str(st.get("error") or "")}})
        new = sorted(str(p.relative_to(self.root)) for p in work.rglob("*") if p.is_file() and p not in before
                     and ".git" not in p.parts and "artifacts" not in p.parts)
        ok = not summary.get("error") and summary.get("ok", True) is not False and not summary.get("stopped")
        return self._report(kind, summary, new, ok), new, ok

    def _report(self, kind: str, s: dict, files: list[str], ok: bool) -> str:
        if s.get("refused") or (s.get("error") and "won't" in str(s.get("error"))):
            return f"I can't do that one: {s.get('error')}"
        if not ok:
            return f"That didn't work: {s.get('error') or s.get('stopped') or 'see the log'}."
        if kind == "animate":
            c = s.get("check", {})
            verbs = {"bounce": "bounces", "jump": "jumps", "spin": "spins", "pulse": "pulses", "slide": "slides", "float": "floats",
                     "orbit": "orbits", "shake": "shakes", "fade": "fades", "grow": "grows", "walk": "walks", "run": "runs",
                     "wave": "waves"}
            subj = {"stickman": "stick figure", "dots": "set of loading dots"}.get(s.get("subject"), s.get("subject"))
            n = (s.get("check") or {}).get("count") or s.get("count") or 1
            what = f"a {subj} that {' and '.join(verbs.get(m, m) for m in s.get('motions', []))}" if n == 1 or s.get("subject") == "dots" \
                else f"{n} {subj}s that {' and '.join(verbs.get(m, m).rstrip('s') if not m.endswith('s') else m for m in s.get('motions', []))}"
            return (f"Done: {what}, {c.get('frames')} frames, "
                    f"checked that it moves{'' if not c.get('touches_edge') else ' (it touches the edge)'}. "
                    f"Files: {s.get('html')} and {s.get('gif')}.")
        if kind == "design_page":
            keep = [f for f in files if not re.search(r"/alt\.(html|png)$", f)]
            return f"Designed it; design check score {s.get('critique_after')}/100. Files: {', '.join(keep[:4])}."
        if kind == "write_code":
            return (f"Wrote {s.get('file')}; tests {'passed' if s.get('ok') else 'failed'}"
                    f"{' on attempt ' + str(s.get('passed_on_attempt')) if s.get('passed_on_attempt') else ''}"
                    f"{' (tests written by the model: review them)' if s.get('warning') else ''}.")
        if kind == "fix_tests":
            return f"{'Fixed' if s.get('fixed') else 'Could not fix'} {s.get('file') or 'the failing tests'}."
        if kind == "build_app":
            return f"Built it; tests {'pass' if s.get('tests_after') else 'fail'}, critique {s.get('critique_after')}. Files: {', '.join(files[:5])}."
        if kind == "unknown":
            return ("I don't know how to do that yet. I can: make animations, design pages, write code, fix tests, build "
                    "small apps.")
        return f"Done. Files: {', '.join(files[:6]) or '(none)'}."

    # ---- local voice for characters: rules decide, the local model rephrases (numbers must survive)
    def _voice(self, line: str, message: str, voice=None) -> str | None:
        try:
            if voice is None:
                from xon import config
                from xon.lm.pretrained import load
                voice = load(config.load(self.root) if (self.root / "xon.toml").exists() else config.load())
            if voice is None:
                return None
            out = voice.chat([{"role": "system", "content": f"You are {self.spec['persona']}. Rewrite the line in your own "
                               "voice, one or two sentences. Keep every number and item name exactly."},
                              {"role": "user", "content": f"Player said: {message}\nYour line: {line}"}], max_new=80).strip()
            nums = set(re.findall(r"\d+", line))
            if out and nums <= set(re.findall(r"\d+", out)) and len(out) < 400:
                return out.strip('"')
        except Exception:
            return None
        return None

    def _rules(self, message: str, player: str, actions: list) -> str:
        role = self.spec["role"]
        if role in ("shopkeeper", "blacksmith", "innkeeper"):
            return _shop_policy(self, message, player, actions)
        if role == "guard":
            return _guard_policy(self, message, player, actions)
        if role == "questgiver":
            return _quest_policy(self, message, player, actions)
        if re.search(r"\b(hi|hello|hey|greetings)\b", message.lower()):
            return f"Hello there, I'm {self.name}."
        return f"I'm {self.name}. Give me a game tool to work with and I'll use it."


_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "a couple of": 2, "a few": 3}


def _qty(text: str) -> int:
    text = re.sub(r"(?:for|at|offer|pay|give you)?\s*\d+\s*(?:gold|g\b|coins?)", " ", text)  # prices are not quantities
    m = re.search(r"\b(\d+)\s*(?:x\b)?", text)
    if m:
        return max(1, int(m.group(1)))
    for w, n in sorted(_NUMS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{w}\b", text):
            return n
    return 1


def _offer(text: str) -> int | None:
    m = re.search(r"(?:for|at|offer|pay|give you)\s+(\d+)\s*(?:gold|g\b|coins?)?|(\d+)\s*(?:gold|g\b|coins?)", text)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _match_item(text: str, items: list[str]) -> str | None:
    t = text.lower()
    for it in sorted(items, key=len, reverse=True):  # exact or plural mention first
        if it in t or it + "s" in t or it.split()[-1] + "s" in t.split() or it.split()[-1] in t.split():
            return it
    words = re.findall(r"[a-z]+", t)
    best, score = None, 0.0
    for it in items:
        for w in words:
            for part in it.split():
                s = difflib.SequenceMatcher(None, w, part).ratio()
                if s > score and len(w) > 3:
                    best, score = it, s
    return best if score >= 0.8 else None


def _shop_policy(sa: SubAgent, msg: str, player: str, actions: list) -> str:
    t = msg.lower()
    mem = sa.memory.setdefault(player, {"turns": [], "pending": None})
    inv = sa.call("shop_inventory", {}, actions) if "shop_inventory" in sa.spec["tools"] else {"items": []}
    items = {i["item"]: i for i in inv.get("items", [])}
    stock_names = list(items)
    item = _match_item(t, stock_names)
    name = sa.name

    pending = mem.get("pending")
    if pending and re.search(r"\b(yes|deal|ok|okay|sure|fine|agreed|i'll take it|done)\b", t):
        mem["pending"] = None
        r = sa.call("sell_to_player", {"player": player, "item": pending["item"], "qty": pending["qty"],
                                       "price_each": pending["price_each"]}, actions)
        if r.get("ok"):
            return f"Pleasure doing business! {r['qty']} x {r['sold']} for {r['total']} gold. You have {r['player_gold']} left."
        return f"Ah, that won't work: {r.get('error')}."
    if pending and re.search(r"\b(no|nah|nope|never mind|too much|pass)\b", t):
        mem["pending"] = None
        return "Suit yourself. The offer stands if you change your mind."

    if re.search(r"\b(sell (you|my|this|these)|buy (my|this|these)|want to sell|i'?d like to sell|trade in)\b", t):
        bag = sa.call("player_wallet", {"player": player}, actions).get("bag", {}) if "player_wallet" in sa.spec["tools"] else {}
        it = _match_item(t, list(bag)) or _match_item(t, stock_names)
        if not it:
            return "What are you selling? I don't see it in your bag."
        if "buy_from_player" not in sa.spec["tools"]:
            return "Sorry, I'm not allowed to buy from customers."
        r = sa.call("buy_from_player", {"player": player, "item": it, "qty": _qty(t)}, actions)
        if r.get("ok"):
            return f"I'll take {r['qty']} x {r['bought']} off your hands for {r['total']} gold. You now have {r['player_gold']}."
        return f"Can't do that: {r.get('error')}."

    wants_buy = re.search(r"\b(buy|purchase|i'?ll take|i want|i'?d like|give me|get me|need|can i (get|have))\b", t)
    asks_price = re.search(r"\b(how much|price|cost|costs|what'?s .* worth)\b", t)
    if item and (wants_buy or _offer(t) is not None) and not asks_price:
        it = items[item]
        qty = _qty(t.replace(item, ""))
        offer = _offer(t)
        if offer is None:
            each = it["price"]
        elif qty > 1 and offer >= it["price"] * qty * 0.5:  # "3 potions for 40 gold" = a total
            each = max(1, round(offer / qty))
        else:
            each = offer
        if offer is not None and each < it["price"]:
            if each >= it["price"] * 0.85:
                pass  # accept the haggle
            else:
                counter = max(int(it["price"] * 0.92), int(it["price"] * 0.7))
                mem["pending"] = {"item": item, "qty": qty, "price_each": counter}
                return f"{each} gold? You wound me. I can do {counter} each for the {item}, final offer. Deal?"
        r = sa.call("sell_to_player", {"player": player, "item": item, "qty": qty, "price_each": each}, actions)
        if r.get("ok"):
            return f"Here you go: {r['qty']} x {r['sold']} for {r['total']} gold. You have {r['player_gold']} gold left."
        if "needs" in str(r.get("error", "")):
            w = sa.call("player_wallet", {"player": player}, actions) if "player_wallet" in sa.spec["tools"] else {}
            return f"That's {each * qty} gold and you've only got {w.get('gold', 'not enough')}. Come back with more coin."
        return f"Sorry, {r.get('error')}."
    if item and (asks_price or re.search(r"\b(tell me about|what about)\b", t)):
        r = sa.call("check_price", {"item": item}, actions) if "check_price" in sa.spec["tools"] else items[item]
        return f"The {item} is {r['price']} gold. I have {r['qty']} in stock."
    if re.search(r"\b(discount|cheaper|lower|deal|haggle|bargain)\b", t) and item:
        it = items[item]
        counter = int(it["price"] * 0.92)
        mem["pending"] = {"item": item, "qty": 1, "price_each": counter}
        return f"For you? {counter} gold for the {item}, and not a coin less. Deal?"
    if re.search(r"\b(what do you (sell|have|got)|wares|stock|inventory|show me|for sale|what.*(sell|have))\b", t) or (
            wants_buy and not item):
        if not items:
            return "My shelves are empty right now, sorry."
        listing = ", ".join(f"{i} ({v['price']}g)" for i, v in list(items.items())[:7])
        return f"Take a look: {listing}."
    if re.search(r"\b(gold|money|how rich|my wallet|how much do i have)\b", t) and "player_wallet" in sa.spec["tools"]:
        w = sa.call("player_wallet", {"player": player}, actions)
        return f"By my count you've got {w.get('gold')} gold."
    if re.search(r"\b(restock|more stock|run out|sold out)\b", t) and item and "shop_restock" in sa.spec["tools"]:
        r = sa.call("shop_restock", {"item": item, "qty": 5}, actions)
        return f"Restocked: {r.get('qty')} {item} on the shelf now." if r.get("ok") else f"Can't restock: {r.get('error')}."
    if re.search(r"\b(bye|goodbye|farewell|see you|later)\b", t):
        return "Safe travels! Come back soon."
    if re.search(r"\b(hi|hello|hey|greetings|good (morning|evening|day))\b", t):
        return f"Welcome to my shop! I'm {name}. Looking for anything in particular?"
    if re.search(r"\b(gate|quest|open)\b", t):
        return "That's not my business, friend. Ask the guard or the elder. I just run the shop."
    if item is None and wants_buy:
        return "I don't carry that. Ask me what I sell."
    return "Hm? If you want to buy or sell, just say so."


def _guard_policy(sa: SubAgent, msg: str, player: str, actions: list) -> str:
    t = msg.lower()
    if re.search(r"\bopen\b", t):
        reason = re.sub(r"^.*?\b(because|for|to)\b", r"\1", msg, count=1) if re.search(r"\b(because|for|to)\b", t) else ""
        if not reason:
            return "And why should I open the gate? Give me a reason."
        r = sa.call("open_gate", {"reason": reason[:120]}, actions)
        return "Very well. The gate is open. Move along." if r.get("ok") else f"I can't: {r.get('error')}."
    if re.search(r"\bclose\b", t):
        r = sa.call("close_gate", {}, actions)
        return "Gate's shut." if r.get("ok") else f"I can't: {r.get('error')}."
    if re.search(r"\b(buy|sell|price|shop)\b", t):
        return "I'm a guard, not a merchant. The shop's down the road."
    return f"Halt. I'm {sa.name} of the town watch. State your business."


def _quest_policy(sa: SubAgent, msg: str, player: str, actions: list) -> str:
    t = msg.lower()
    if re.search(r"\b(quest|job|work|task|mission|help)\b", t):
        r = sa.call("give_quest", {"player": player, "quest": "Clear the rats from the old cellar", "reward_gold": 40}, actions)
        return ("Rats have taken the old cellar. Clear them out and 40 gold is yours." if r.get("ok")
                else f"Not now: {r.get('error')}.")
    return f"Greetings, traveller. I'm {sa.name}. Looking for work?"
