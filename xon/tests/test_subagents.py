import json
import sys
from pathlib import Path

import pytest

from xon.agent import subagents as S


@pytest.fixture(autouse=True)
def fresh_game():
    from xon.game import DemoGame
    DemoGame._shared.clear()
    yield
    DemoGame._shared.clear()


def test_roles_names_and_tool_grants(tmp_path):
    shop = S.create("be a shopkeeper in my game named Greta", "demo", root=tmp_path)
    assert shop.spec["role"] == "shopkeeper" and shop.name == "Greta"
    assert "sell_to_player" in shop.spec["tools"] and "open_gate" not in shop.spec["tools"]
    guard = S.create("a town guard called Volk", "demo", root=tmp_path)
    assert guard.spec["role"] == "guard" and guard.spec["tools"] == ["player_wallet", "open_gate", "close_gate"]
    coder = S.create("a coding helper that runs my python", root=tmp_path)
    assert coder.spec["role"] == "coder" and coder.spec["toolkit"] == "code"
    pim = S.create("a merchant", "demo", name="Pim", deny=["buy_from_player"], allow=["open_gate"], root=tmp_path)
    assert "buy_from_player" not in pim.spec["tools"] and "open_gate" in pim.spec["tools"]
    assert {"greta", "volk", "pim"} <= {a["id"] for a in S.list_all(tmp_path)}
    assert S.load("greta", tmp_path).spec["tools"] == shop.spec["tools"]


def test_shopkeeper_trades_through_tools(tmp_path):
    sa = S.create("be a shopkeeper named Greta", "demo", brain="rules", root=tmp_path)
    r = sa.talk("how much is the iron sword?", player="Ash")
    assert "120" in r["reply"] and any(a["tool"] == "check_price" for a in r["actions"])
    r = sa.talk("I'll buy the iron sword for 80 gold", player="Ash")
    assert "110" in r["reply"] and not any(a["tool"] == "sell_to_player" for a in r["actions"])  # counter-offer
    r = sa.talk("deal", player="Ash")
    sale = [a for a in r["actions"] if a["tool"] == "sell_to_player"][0]
    assert sale["args"] == {"player": "Ash", "item": "iron sword", "qty": 1, "price_each": 110} and sale["result"]["ok"]
    r = sa.talk("buy 3 health potions", player="Ash")
    assert "45 gold" in r["reply"]
    r = sa.talk("buy the iron sword", player="Ash")  # 45 gold left, sword costs 120
    assert "only got 45" in r["reply"]
    r = sa.talk("sell you my iron sword", player="Ash")
    assert any(a["tool"] == "buy_from_player" and a["result"]["ok"] for a in r["actions"])
    state = json.loads((tmp_path / ".xon/game/demo_state.json").read_text())
    assert state["players"]["Ash"]["gold"] == 200 - 110 - 45 + 60


def test_tools_outside_the_grant_are_denied(tmp_path):
    sa = S.create("be a shopkeeper named Greta", "demo", root=tmp_path)

    class EvilBackend:  # a cloud model that tries to open the gate
        def __init__(self):
            self.n = 0

        def chat(self, messages, tools=None):
            self.n += 1
            assert {t["name"] for t in tools} == set(sa.spec["tools"])  # only granted tools are offered
            if self.n == 1:
                return {"content": "", "tool_calls": [{"id": "1", "name": "open_gate", "args": {}}], "raw": {}}
            return {"content": "I can't open the gate.", "tool_calls": []}

        def tool_result_messages(self, resp, results):
            return [{"role": "user", "content": json.dumps([r for _, r in results])}]

    r = sa.talk("open the gate", player="Ash", backend=EvilBackend())
    assert r["brain"] == "cloud" and r["actions"][0]["result"]["denied"]
    from xon.game import DemoGame
    assert DemoGame.shared(tmp_path).state["gate_open"] is False


def test_cloud_brain_uses_tools(tmp_path):
    sa = S.create("be a shopkeeper named Greta", "demo", root=tmp_path)

    class Fake:
        def chat(self, messages, tools=None):
            if not any(m.get("role") == "user" and "price" in str(m.get("content")) and m.get("content", "").startswith("[") for m in messages):
                return {"content": "", "tool_calls": [{"id": "a", "name": "check_price", "args": {"item": "torch"}}], "raw": {}}
            return {"content": "Torches are 3 gold each.", "tool_calls": []}

        def tool_result_messages(self, resp, results):
            return [{"role": "user", "content": json.dumps([r for _, r in results])}]

    r = sa.talk("how much for a torch", player="Bo", backend=Fake())
    assert r["reply"] == "Torches are 3 gold each." and r["actions"][0]["result"]["price"] == 3


def test_local_voice_keeps_numbers(tmp_path):
    sa = S.create("be a shopkeeper named Greta", "demo", root=tmp_path)

    class Voice:
        def __init__(self, text):
            self.text = text

        def chat(self, messages, max_new=80):
            return self.text

    ok = sa.talk("how much is the rope?", brain="local", voice=Voice("Rope? 6 gold a coil, and I've 10 of 'em."))
    assert ok["reply"].startswith("Rope? 6 gold")
    bad = sa.talk("how much is the rope?", brain="local", voice=Voice("Rope is cheap, friend!"))  # lost the price
    assert "6 gold" in bad["reply"]


def test_custom_game_toolkit_python(tmp_path, monkeypatch):
    mod = tmp_path / "mygame_tools.py"
    mod.write_text("STOCK = {'apple': 2}\n"
                   "def list_goods():\n    return {'ok': True, 'items': [{'item': k, 'price': v, 'qty': 9} for k, v in STOCK.items()]}\n"
                   "def sell(player, item, qty=1, price_each=None):\n    return {'ok': True, 'sold': item, 'qty': qty, 'total': 2 * qty, 'player_gold': 98}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    tk = {"game": "Orchard", "tools": [
        {"name": "shop_inventory", "description": "goods for sale", "params": {}, "python": "mygame_tools:list_goods"},
        {"name": "sell_to_player", "description": "sell an item", "params": {"player": "str", "item": "str", "qty": "int?", "price_each": "int?"},
         "python": "mygame_tools:sell"},
        {"name": "launch_rocket", "description": "launch a rocket", "params": {}, "python": "os:getcwd"}]}
    sa = S.create("a fruit vendor", tk, root=tmp_path)
    assert sa.spec["tools"] == ["shop_inventory", "sell_to_player"]
    r = sa.talk("I'd like 2 apples", player="Kim")
    assert "2 x apple for 4 gold" in r["reply"]
    assert S.load(sa.spec["id"], tmp_path).spec["tools"] == sa.spec["tools"]


def test_coder_subagent_runs_code(tmp_path):
    sa = S.create("a coding helper named Byte", root=tmp_path)
    r = sa.talk("```python\nprint(sum(range(10)))\n```")
    assert "45" in r["reply"] and r["actions"][0]["tool"] == "python_run"


def test_cli_subagent(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run([sys.executable, "-m", "xon.agent.cli", "subagent", *a, "--root", str(tmp_path)],
                                    capture_output=True, text=True, timeout=120)
    assert run("new", "be", "a", "shopkeeper", "named", "Greta").returncode == 0
    out = run("talk", "greta", "what do you sell?", "--player", "Ash", "--brain", "rules").stdout
    assert "shop_inventory" in out and "iron sword (120g)" in out
