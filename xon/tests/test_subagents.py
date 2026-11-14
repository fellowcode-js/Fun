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
    assert coder.spec["role"] == "coder" and coder.is_specialist and "codegen" in coder.spec["tools"]
    pim = S.create("a merchant", "demo", name="Pim", deny=["buy_from_player"], allow=["open_gate"], root=tmp_path)
    assert "buy_from_player" not in pim.spec["tools"] and "open_gate" in pim.spec["tools"]
    assert {"greta", "volk", "pim"} <= {a["id"] for a in S.list_all(tmp_path)}
    assert S.load("greta", tmp_path).spec["tools"] == shop.spec["tools"]


def test_shopkeeper_trades_through_tools(tmp_path):
    sa = S.create("be a shopkeeper named Greta", "demo", root=tmp_path)
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


def test_cli_subagent(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run([sys.executable, "-m", "xon.agent.cli", "subagent", *a, "--root", str(tmp_path)],
                                    capture_output=True, text=True, timeout=120)
    assert run("new", "be", "a", "shopkeeper", "named", "Greta").returncode == 0
    out = run("talk", "greta", "what do you sell?", "--player", "Ash", "--brain", "rules").stdout
    assert "shop_inventory" in out and "iron sword (120g)" in out


def test_tool_outside_the_grant_is_denied(tmp_path):
    sa = S.create("be a shopkeeper in my game named Greta", "demo", root=tmp_path)
    acts = []
    r = sa.call("open_gate", {}, acts)
    assert r["denied"] and acts[0]["tool"] == "open_gate"
    from xon.game import DemoGame
    assert DemoGame.shared(tmp_path).state["gate_open"] is False


def test_specialist_roles_from_any_task(tmp_path):
    cases = {"a helper that makes animations": ("animator", "animate"), "someone to design landing pages": ("designer", "design"),
             "a debugger for my failing tests": ("tester", "fix"), "a helper that tidies my notes": ("helper", "read")}
    for task, (role, tool) in cases.items():
        sa = S.create(task, root=tmp_path)
        assert sa.spec["role"] == role and sa.is_specialist and tool in sa.spec["tools"], task
        assert "subagent" not in sa.spec["tools"] and "shop_inventory" not in sa.spec["tools"]
    anim = S.create("a helper that makes animations", root=tmp_path)
    assert "codegen" not in anim.spec["tools"] and "shell" not in anim.spec["tools"]  # only what animation needs


def test_animator_makes_animations(tmp_path):
    sa = S.create("a helper that makes animations named Pixel", root=tmp_path)
    r = sa.talk("a red ball bouncing")
    assert r["ok"] and "bounces" in r["reply"]
    assert any(f.endswith(".gif") for f in r["files"]) and any(f.endswith(".html") for f in r["files"])
    assert all(f.startswith("subagents/pixel/") for f in r["files"])
    assert any(a["tool"] == "animate" for a in r["actions"])
    r2 = sa.talk("design a pricing page")  # outside its specialty: it still animates, never designs
    assert not any(a["tool"] == "design" for a in r2["actions"])
    bad = sa.talk("make mario jumping")
    assert not bad["ok"] and "copyrighted" in bad["reply"]


def test_xon_spawns_and_delegates(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    from xon.agent.loop import Agent
    ag = Agent(tmp_path, mode="auto-edit", assume_yes=True)
    r = ag.run("make a sub-agent that makes animations named Flip and have it make three yellow stars spinning")
    assert r["created"] == "flip" and r["role"] == "animator"
    assert "stars" in " ".join(r["first_job"]["files"]) and "spins" in r["first_job"]["reply"]
    r = ag.run("ask Flip to make a stick figure walking")
    assert r["ok"] and "walks" in r["reply"]
    r = ag.run("ask Nobody to make a ball")
    assert not r["ok"] and "You have: Flip" in r["error"]


def test_local_only_never_uses_cloud(monkeypatch, home):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-used")
    from xon.agent.backends import local_only, pick
    assert local_only(home)
    assert pick("auto", home).name == "rules" and pick("anthropic", home).name == "rules"
    from xon.agent.loop import Agent
    assert Agent(home["_root"], home).backend.name == "rules"
