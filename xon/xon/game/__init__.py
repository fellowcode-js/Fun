"""Game toolkits: the tools a sub-agent (an NPC) may use inside your game.

A toolkit is a list of tools. Each tool has a name, a description, params ({"name": "str|int|float|bool", "?" =
optional}) and one way to run it:
  "http":   {"url": "http://127.0.0.1:7777/shop/sell", "method": "POST"}   your game's server gets the args as JSON
  "python": "mygame.npc_tools:sell_item"                                   an importable function(**args) -> dict
  builtin:  the demo game below (`toolkit("demo")`), so everything can be tried without a game

Write your own as game_tools.json:
  {"game": "My Game", "tools": [{"name": "shop_inventory", "description": "...", "params": {},
                                  "http": {"url": "http://127.0.0.1:7777/npc/shop_inventory"}}]}

A sub-agent only ever gets the tools it was granted; Toolkit.call refuses everything else.
"""
from __future__ import annotations

import importlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests


class ToolDenied(PermissionError):
    pass


@dataclass
class GameTool:
    name: str
    description: str
    params: dict = field(default_factory=dict)
    fn: Callable[..., dict] | None = None
    http: dict | None = None
    python: str | None = None

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "params": self.params}

    def run(self, **args) -> dict:
        if self.fn is not None:
            return self.fn(**args)
        if self.python:
            mod, _, attr = self.python.partition(":")
            return getattr(importlib.import_module(mod), attr)(**args)
        if self.http:
            method = self.http.get("method", "POST").upper()
            r = requests.request(method, self.http["url"], json=args if method != "GET" else None,
                                 params=args if method == "GET" else None, timeout=float(self.http.get("timeout", 10)))
            r.raise_for_status()
            try:
                return r.json()
            except ValueError:
                return {"text": r.text[:4000]}
        raise RuntimeError(f"tool {self.name} has no implementation")


class Toolkit:
    def __init__(self, game: str, tools: list[GameTool]):
        self.game = game
        self.tools = {t.name: t for t in tools}

    def specs(self, names: list[str] | None = None) -> list[dict]:
        return [t.spec() for n, t in self.tools.items() if names is None or n in names]

    def call(self, name: str, args: dict, allowed: list[str]) -> dict:
        if name not in allowed:
            raise ToolDenied(f"tool '{name}' was not granted to this sub-agent")
        if name not in self.tools:
            raise KeyError(f"no tool '{name}' in toolkit '{self.game}'")
        want = self.tools[name].params
        clean = {k: v for k, v in (args or {}).items() if k in want}
        missing = [k for k, t in want.items() if not str(t).endswith("?") and k not in clean]
        if missing:
            return {"ok": False, "error": f"missing argument(s): {', '.join(missing)}"}
        try:
            return self.tools[name].run(**clean)
        except ToolDenied:
            raise
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def load_toolkit(src: str | Path | dict | None, root: Path | None = None) -> Toolkit:
    """"demo" (built-in shop game), a path to game_tools.json, or an already-parsed dict."""
    if src in (None, "", "demo"):
        return DemoGame.shared(root).toolkit()
    if src == "code":
        from xon.game.code_tools import toolkit as code_toolkit
        return code_toolkit(root)
    d = src if isinstance(src, dict) else json.loads(Path(src).read_text())
    tools = []
    for t in d.get("tools", []):
        if not (t.get("http") or t.get("python")):
            raise ValueError(f"tool {t.get('name')} needs an 'http' or 'python' entry")
        tools.append(GameTool(t["name"], t.get("description", ""), t.get("params", {}), http=t.get("http"),
                              python=t.get("python")))
    return Toolkit(d.get("game", "game"), tools)


# --------------------------------------------------------------------------------------------- demo game

DEFAULT_STOCK = {
    "iron sword": {"price": 120, "qty": 3},
    "wooden shield": {"price": 45, "qty": 5},
    "health potion": {"price": 15, "qty": 20},
    "mana potion": {"price": 18, "qty": 12},
    "leather boots": {"price": 35, "qty": 4},
    "torch": {"price": 3, "qty": 40},
    "rope": {"price": 6, "qty": 10},
}


class DemoGame:
    """A tiny in-memory RPG town: one shop, a gate, a quest board and player wallets/bags. Saved to JSON."""
    _shared: dict[str, "DemoGame"] = {}

    def __init__(self, path: Path | None = None):
        self.path = path
        self.lock = threading.Lock()
        self.state = {"shop": {"gold": 500, "stock": json.loads(json.dumps(DEFAULT_STOCK))},
                      "players": {}, "gate_open": False, "log": []}
        if path and path.exists():
            try:
                self.state.update(json.loads(path.read_text()))
            except ValueError:
                pass

    @classmethod
    def shared(cls, root: Path | None = None) -> "DemoGame":
        key = str(root or "")
        if key not in cls._shared:
            p = (Path(root) / ".xon" / "game" / "demo_state.json") if root else None
            cls._shared[key] = cls(p)
        return cls._shared[key]

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.state, indent=1))

    def player(self, name: str) -> dict:
        return self.state["players"].setdefault(name or "player", {"gold": 200, "bag": {}})

    def _event(self, text: str):
        self.state["log"] = (self.state["log"] + [text])[-50:]

    # ---- tools
    def shop_inventory(self) -> dict:
        s = self.state["shop"]
        return {"ok": True, "shop_gold": s["gold"],
                "items": [{"item": k, "price": v["price"], "qty": v["qty"]} for k, v in s["stock"].items() if v["qty"] > 0]}

    def check_price(self, item: str) -> dict:
        it = self.state["shop"]["stock"].get(item)
        if not it:
            return {"ok": False, "error": f"the shop does not stock '{item}'"}
        return {"ok": True, "item": item, "price": it["price"], "qty": it["qty"]}

    def player_wallet(self, player: str) -> dict:
        p = self.player(player)
        return {"ok": True, "player": player, "gold": p["gold"], "bag": p["bag"]}

    def sell_to_player(self, player: str, item: str, qty: int = 1, price_each: int | None = None) -> dict:
        with self.lock:
            s, p = self.state["shop"], self.player(player)
            it = s["stock"].get(item)
            qty = max(1, int(qty))
            if not it or it["qty"] < qty:
                return {"ok": False, "error": f"not enough '{item}' in stock"}
            each = int(price_each if price_each is not None else it["price"])
            if each < int(it["price"] * 0.7):
                return {"ok": False, "error": f"the shop will not sell '{item}' below {int(it['price'] * 0.7)} gold"}
            total = each * qty
            if p["gold"] < total:
                return {"ok": False, "error": f"{player} has {p['gold']} gold, needs {total}"}
            p["gold"] -= total
            s["gold"] += total
            it["qty"] -= qty
            p["bag"][item] = p["bag"].get(item, 0) + qty
            self._event(f"{player} bought {qty} x {item} for {total}")
            self.save()
            return {"ok": True, "sold": item, "qty": qty, "total": total, "player_gold": p["gold"]}

    def buy_from_player(self, player: str, item: str, qty: int = 1, price_each: int | None = None) -> dict:
        with self.lock:
            s, p = self.state["shop"], self.player(player)
            qty = max(1, int(qty))
            if p["bag"].get(item, 0) < qty:
                return {"ok": False, "error": f"{player} does not have {qty} x '{item}'"}
            base = s["stock"].get(item, {}).get("price", 10)
            each = int(price_each if price_each is not None else base // 2)
            each = min(each, int(base * 0.6))  # shops buy cheap
            total = each * qty
            if s["gold"] < total:
                return {"ok": False, "error": "the shop cannot afford that right now"}
            p["bag"][item] -= qty
            if not p["bag"][item]:
                del p["bag"][item]
            p["gold"] += total
            s["gold"] -= total
            s["stock"].setdefault(item, {"price": base, "qty": 0})["qty"] += qty
            self._event(f"{player} sold {qty} x {item} for {total}")
            self.save()
            return {"ok": True, "bought": item, "qty": qty, "total": total, "player_gold": p["gold"]}

    def restock(self, item: str, qty: int = 5) -> dict:
        with self.lock:
            it = self.state["shop"]["stock"].setdefault(item, {"price": 10, "qty": 0})
            cost = it["price"] // 2 * int(qty)
            if self.state["shop"]["gold"] < cost:
                return {"ok": False, "error": "not enough shop gold to restock"}
            self.state["shop"]["gold"] -= cost
            it["qty"] += int(qty)
            self.save()
            return {"ok": True, "item": item, "qty": it["qty"], "cost": cost}

    def open_gate(self, reason: str = "") -> dict:
        self.state["gate_open"] = True
        self._event(f"gate opened ({reason})")
        self.save()
        return {"ok": True, "gate_open": True}

    def close_gate(self) -> dict:
        self.state["gate_open"] = False
        self.save()
        return {"ok": True, "gate_open": False}

    def give_quest(self, player: str, quest: str, reward_gold: int = 50) -> dict:
        p = self.player(player)
        p.setdefault("quests", []).append({"quest": quest, "reward": int(reward_gold)})
        self.save()
        return {"ok": True, "player": player, "quest": quest, "reward_gold": int(reward_gold)}

    def toolkit(self) -> Toolkit:
        T = GameTool
        return Toolkit("demo town", [
            T("shop_inventory", "List what the shop sells: item, price, quantity, and the shop's gold.", {}, self.shop_inventory),
            T("check_price", "Price and stock of one item.", {"item": "str"}, self.check_price),
            T("player_wallet", "A player's gold and bag.", {"player": "str"}, self.player_wallet),
            T("sell_to_player", "The shop sells an item to a player (takes their gold). price_each defaults to list price; "
              "never below 70% of it.", {"player": "str", "item": "str", "qty": "int?", "price_each": "int?"}, self.sell_to_player),
            T("buy_from_player", "The shop buys an item from a player (at most 60% of list price).",
              {"player": "str", "item": "str", "qty": "int?", "price_each": "int?"}, self.buy_from_player),
            T("shop_restock", "Restock an item, paying half its price per unit from the shop's gold.",
              {"item": "str", "qty": "int?"}, self.restock),
            T("open_gate", "Open the town gate.", {"reason": "str?"}, self.open_gate),
            T("close_gate", "Close the town gate.", {}, self.close_gate),
            T("give_quest", "Give a player a quest with a gold reward.", {"player": "str", "quest": "str", "reward_gold": "int?"},
              self.give_quest),
        ])
