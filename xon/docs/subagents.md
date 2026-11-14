# Sub-agents

XON can spawn a role-playing sub-agent from one line, the way Claude spawns sub-agents for a task, and give it only
the tools that role needs. Built for game NPCs (a shopkeeper that really sells from your game's shop), also works
for helpers (a coder that runs code). Code: `xon/agent/subagents.py`, `xon/game/`. Tests: `tests/test_subagents.py`.

## Try it
```bash
xon subagent new "be a shopkeeper in my game named Greta"          # built-in demo town
xon subagent talk greta --player Ash                                # chat in the terminal
xon subagent talk greta "I'll buy the iron sword for 80 gold"       # or one line
xon subagent list
xon subagent new "a town guard called Volk"
xon subagent new "a coding helper named Byte"                        # gets the code toolkit
xon subagent new "a merchant" --name Pim --deny buy_from_player --allow open_gate
```
Or open XON Studio -> **Sub-agents**: spawn, talk as a player, watch every tool call and the game world update.

## What the task decides
| Task mentions | Role | Tools it gets from the demo town |
|---|---|---|
| shop, merchant, vendor, store, sell | shopkeeper | shop_inventory, check_price, player_wallet, sell_to_player, buy_from_player, shop_restock |
| blacksmith, forge | blacksmith | same shop tools |
| inn, tavern | innkeeper | shop tools + give_quest |
| guard, gate, sentry | guard | open_gate, close_gate, player_wallet |
| quest, elder, mission | questgiver | give_quest, player_wallet |
| code, programmer, debug | coder | python_run, cpp_run, write_code (code toolkit) |
| anything else | npc | none unless you `--allow` them |
"named X" / "called X" sets the name. A tool that was not granted is refused even if the brain asks for it (the
test `test_tools_outside_the_grant_are_denied` has a cloud model try to open the gate as the shopkeeper).

## Brains
- **rules** (default without a key, offline): parses the player's line and calls tools. Prices, items and gold
  always come from tool results, never made up. The shopkeeper haggles (accepts 85%+ of list, otherwise counters
  at 92% and remembers the offer, so "deal" closes it), buys back at up to 60%, and refuses jobs that are not hers.
- **local**: rules decide the actions, the local Qwen model rewrites the line in the persona's voice. If the rewrite
  drops a number, the plain line is used instead.
- **cloud**: Claude (or OpenAI-compatible) with native tool calling, only the granted tools offered. Best for free
  conversation. Needs `ANTHROPIC_API_KEY` or a key in Studio -> Connect. `auto` picks cloud when a key exists.

## Hook it to your game
Describe your game's tools in `game_tools.json`. Each tool is either an HTTP endpoint on your game server (the args
arrive as JSON) or an importable Python function:
```json
{"game": "My RPG",
 "tools": [
  {"name": "shop_inventory", "description": "What the shop sells", "params": {},
   "http": {"url": "http://127.0.0.1:7777/npc/shop_inventory"}},
  {"name": "sell_to_player", "description": "Sell an item to a player",
   "params": {"player": "str", "item": "str", "qty": "int?", "price_each": "int?"},
   "http": {"url": "http://127.0.0.1:7777/npc/sell"}},
  {"name": "open_gate", "description": "Open the town gate", "params": {}, "python": "mygame.npc:open_gate"}
 ]}
```
```bash
xon subagent new "be the shopkeeper of Riverbend" --toolkit game_tools.json
```
Your game then talks to the NPC through Studio's API (`xon studio --token YOURTOKEN`):
```
POST http://127.0.0.1:8790/api/subagents/talk   header X-XON-Token: YOURTOKEN
{"id": "greta", "player": "Ash", "message": "how much is the sword?"}
-> {"reply": "...", "actions": [{"tool": "check_price", "args": {...}, "result": {...}}], "brain": "rules"}
```
Tool names that match the demo's (`shop_inventory`, `check_price`, `sell_to_player`, ...) work with the offline
rules brain; any other names work with the cloud brain, and are matched to roles by words in their name/description.

## Limits
- The rules brain understands shop/guard/quest/coding phrasing, not open conversation. For that use the cloud brain.
- The demo town is a stand-in; its state lives in `.xon/game/demo_state.json`. Sub-agent specs and per-player
  memory live in `.xon/subagents/`.

Related: [studio.md](studio.md), [exhort.md](exhort.md).
