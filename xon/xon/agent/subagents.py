"""Sub-agents: XON spawns a role-playing agent from a one-line task and gives it only the tools that role needs.

  sa = create("be a shopkeeper in my game named Greta", toolkit="demo")      # or toolkit="game_tools.json"
  sa.talk("hi, how much is the iron sword?", player="Ash")                  # -> reply + the tool calls it made

The task picks a role template (shopkeeper, blacksmith, innkeeper, guard, quest giver, coder, or a generic NPC),
a name, a persona and rules, and grants the toolkit's tools that fit the role (override with allow= / deny=).
A sub-agent can never call a tool it was not granted: Toolkit.call refuses it.

Brains (`brain=`):
  cloud  Claude / OpenAI-compatible model with native tool calling (needs ANTHROPIC_API_KEY or OPENAI_API_KEY)
  rules  deterministic role policy: parses the player's line, calls the tools, answers in character. Works offline,
         never invents prices or items (everything comes from tool results).
  local  rules decide the actions, XON's local coder model rewrites the line in the persona's voice
  auto   cloud if a key is set, else rules
Specs and per-player memory live in <root>/.xon/subagents/.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
from pathlib import Path

from xon.game import Toolkit, ToolDenied, load_toolkit

ROLES: dict[str, dict] = {
    "shopkeeper": {
        "keywords": ["shopkeeper", "shop", "merchant", "vendor", "store", "trader", "seller", "sell", "market", "general store"],
        "tools": ["shop_inventory", "check_price", "player_wallet", "sell_to_player", "buy_from_player", "shop_restock"],
        "tool_words": ["shop", "price", "wallet", "sell", "buy", "inventory", "stock", "trade"],
        "names": ["Greta", "Odo", "Marla", "Pim", "Hollis", "Tamsin", "Bram"],
        "persona": "a friendly but shrewd shopkeeper who knows every item and price on the shelves",
        "rules": ["Only quote prices and items that come from the shop's tools.", "Never sell below the floor price.",
                  "Haggle a little: accept offers of at least 85% of list price, otherwise counter at 92%."],
    },
    "blacksmith": {
        "keywords": ["blacksmith", "smith", "forge", "armorer", "weaponsmith"],
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
    "coder": {
        "keywords": ["coder", "programmer", "code", "coding", "developer", "debug", "reviewer", "python", "c++", "script"],
        "tools": ["python_run", "cpp_run", "write_code"],
        "tool_words": ["run", "code", "test", "compile"],
        "names": ["Byte", "Ada", "Lint"],
        "persona": "a careful coding helper that runs code before claiming it works",
        "rules": ["Run code in the sandbox before saying it works.", "Show the output."],
        "toolkit": "code",
    },
    "npc": {
        "keywords": [],
        "tools": [],
        "tool_words": [],
        "names": ["Wren", "Tobin", "Lark"],
        "persona": "a townsperson",
        "rules": ["Stay in character."],
    },
}


def pick_role(task: str) -> str:
    t = task.lower()
    best, score = "npc", 0
    for role, r in ROLES.items():
        s = sum(2 if re.search(rf"\b{re.escape(k)}\b", t) else 0 for k in r["keywords"])
        s += 1 if role in t else 0
        if s > score:
            best, score = role, s
    return best


def pick_name(task: str, role: str) -> str:
    m = re.search(r"\b(?:named|called|name is|name him|name her|name them)\s+([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)?)", task)
    if m:
        return m.group(1)
    names = ROLES[role]["names"]
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


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "agent"


def _store(root: Path) -> Path:
    d = Path(root) / ".xon" / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(task: str, toolkit: str | dict | None = None, *, name: str | None = None, role: str | None = None,
           allow: list[str] | None = None, deny: list[str] | None = None, brain: str = "auto",
           root: Path | str = ".") -> "SubAgent":
    root = Path(root)
    role = role if role in ROLES else pick_role(task)
    if toolkit in (None, "") and ROLES[role].get("toolkit"):
        toolkit = ROLES[role]["toolkit"]
    toolkit = toolkit or "demo"
    tk = load_toolkit(toolkit, root)
    name = name or pick_name(task, role)
    spec = {
        "id": _slug(name), "name": name, "role": role, "task": task,
        "persona": f"{name}, {ROLES[role]['persona']}",
        "rules": ROLES[role]["rules"], "tools": grant_tools(role, tk, allow, deny),
        "toolkit": toolkit if isinstance(toolkit, str) else "inline", "game": tk.game,
        "brain": brain, "created": time.time(),
    }
    if isinstance(toolkit, dict):
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
    return SubAgent(spec, root, load_toolkit(spec["toolkit"], root))


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
    def __init__(self, spec: dict, root: Path, toolkit: Toolkit):
        self.spec, self.root, self.tk = spec, Path(root), toolkit
        self._mem_path = _store(self.root) / f"{spec['id']}.memory.json"
        self.memory: dict = json.loads(self._mem_path.read_text()) if self._mem_path.exists() else {}

    @property
    def name(self) -> str:
        return self.spec["name"]

    def system_prompt(self) -> str:
        s = self.spec
        return (f"You are {s['persona']} in the game '{s['game']}'. Your job: {s['task']}\n"
                f"Rules:\n- " + "\n- ".join(s["rules"]) +
                "\n- Stay in character; reply in one to three short sentences of spoken dialogue."
                "\n- Use your tools for every fact about the game world (prices, stock, gold). Never invent them."
                "\n- If something needs a tool you do not have, say you can't help with that.")

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
        b = self.spec.get("brain", "auto")
        if b == "auto":
            return "cloud" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("XON_OPENAI_KEY")
                               or os.environ.get("OPENAI_API_KEY")) else "rules"
        return b

    def talk(self, message: str, player: str = "player", brain: str | None = None, backend=None, voice=None) -> dict:
        """One line from a player -> {reply, actions, brain}. `backend`/`voice` let tests inject fakes."""
        t0 = time.time()
        b = brain or ("cloud" if backend is not None else self.brain())
        actions: list[dict] = []
        if b == "cloud":
            try:
                reply = self._cloud(message, player, actions, backend)
            except Exception as e:  # network/key problems: stay playable
                reply = self._rules(message, player, actions)
                b = f"rules (cloud failed: {type(e).__name__})"
        else:
            reply = self._rules(message, player, actions)
            if b == "local":
                reply = self._voice(reply, message, voice) or reply
        self._remember(player, message, reply, actions)
        return {"agent": self.spec["id"], "name": self.name, "reply": reply, "actions": actions, "brain": b,
                "seconds": round(time.time() - t0, 2)}

    # ---- cloud brain: native tool calling
    def _cloud(self, message: str, player: str, actions: list, backend=None) -> str:
        if backend is None:
            from xon.agent.backends import pick
            backend = pick("auto")
            if not hasattr(backend, "chat"):
                raise RuntimeError("no cloud key")
        hist = self.memory.get(player, {}).get("turns", [])[-6:]
        msgs = [{"role": "system", "content": self.system_prompt() + f"\nThe player talking to you is '{player}'."}]
        for t in hist:
            msgs += [{"role": "user", "content": t["player"]}, {"role": "assistant", "content": t["npc"]}]
        msgs.append({"role": "user", "content": message})
        specs = self.tk.specs(self.spec["tools"])
        for _ in range(6):
            r = backend.chat(msgs, tools=specs)
            if not r.get("tool_calls"):
                return (r.get("content") or "...").strip()
            results = [(c, self.call(c["name"], c.get("args") or {}, actions)) for c in r["tool_calls"]]
            msgs += backend.tool_result_messages(r, results)
        return "Give me a moment, I lost my train of thought."

    # ---- local voice: rules decide, the local model rephrases (facts are kept: numbers must survive)
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

    # ---- rules brain
    def _rules(self, message: str, player: str, actions: list) -> str:
        role = self.spec["role"]
        if role in ("shopkeeper", "blacksmith", "innkeeper"):
            return _shop_policy(self, message, player, actions)
        if role == "guard":
            return _guard_policy(self, message, player, actions)
        if role == "questgiver":
            return _quest_policy(self, message, player, actions)
        if role == "coder":
            return _coder_policy(self, message, player, actions)
        if re.search(r"\b(hi|hello|hey|greetings)\b", message.lower()):
            return f"Hello there, I'm {self.name}."
        return f"I'm {self.name}. I don't have a brain for that without a cloud model (set ANTHROPIC_API_KEY)."


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


def _coder_policy(sa: SubAgent, msg: str, player: str, actions: list) -> str:
    block = re.search(r"```(\w*)\n(.*?)```", msg, re.S)
    if block:
        lang = block.group(1).lower()
        tool = "cpp_run" if lang in ("cpp", "c++", "cc") else "python_run"
        r = sa.call(tool, {"code": block.group(2)}, actions)
        out = (r.get("stdout") or "") + (r.get("stderr") or "")
        return f"{'It ran fine' if r.get('ok') else 'It failed'}. Output:\n```\n{out.strip()[-1500:] or '(no output)'}\n```"
    if re.search(r"\b(write|make|create|implement|code)\b", msg.lower()):
        lang = "cpp" if re.search(r"c\+\+|\bcpp\b", msg.lower()) else "python"
        r = sa.call("write_code", {"task": msg, "lang": lang}, actions)
        if not r.get("ok"):
            return f"I can't write code right now: {r.get('error')}."
        verdict = {True: "I ran it and the tests passed", False: "I ran it and the tests FAILED",
                   None: "it has no tests, so I could not check it"}[r.get("tests_passed")]
        out = (r.get("test_output") or "").strip()
        return (f"Here it is ({verdict}):\n```{lang}\n{r['code'].strip()}\n```" +
                (f"\nOutput:\n```\n{out[-800:]}\n```" if out else ""))
    return f"I'm {sa.name}. Paste code in a ``` block and I'll run it, or ask me to write something."
