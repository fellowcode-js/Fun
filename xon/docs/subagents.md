# Sub-agents

XON creates its own helpers. Ask it for a sub-agent for any kind of work, and it works out the specialty, gives
the helper only the XON tools that specialty needs, and gives it its own folder. Then you (or XON) hand it jobs.
Everything runs on your machine: **no API keys, no cloud models** (see [Local only](#local-only)).

Code: `xon/agent/subagents.py`, `xon/agent/tools/subagent.py`, `xon/game/`. Tests: `tests/test_subagents.py`.

## Ask XON for one
```bash
xon agent "make a sub-agent that makes animations named Pixel and have it make a red ball bouncing"
xon agent "ask Pixel to make a stick figure waving hello on a light background"
xon agent "create a helper that designs pages, then a pricing page for a bakery called Crumb with three plans"
```
Or in XON Studio: type the same into **Agent**, or use the **Sub-agents** view (spawn, give jobs, see the GIFs and
pages it makes inline). From the terminal directly:
```bash
xon subagent new "a helper that makes animations"
xon subagent talk pixel "three yellow stars spinning slowly"
xon subagent list
```

## Specialties
| The request mentions | Specialty | XON tools it gets | What a job does |
|---|---|---|---|
| animation, animate, gif, motion, loop | animator | animate, read, write, think, view_image, git | description -> looping animation (`.html` + `.gif`), self-checked |
| design, page, landing, website, UI, screen | designer | design, read, write, edit, think, shell, view_image, git | accessible page, critiqued with computed contrast |
| code, coder, python, c++, function, script | coder | codegen, test, cpp_build, python_run, fix, lint, read, write, edit, think, git | code + tests, run, retry, repair |
| bug, debug, failing tests | tester | test, fix, read, grep, think, git | localize the fault, verify the fix |
| app, builder, tracker | builder | write, read, edit, test, design, think, git | small web app with tests |
| anything else | helper | read, write, edit, glob, grep, think, python_run | what XON's planner recognizes |
| a game role (shopkeeper, guard, innkeeper, quest giver...) | game character | that game's tools (see below) | talks to players, acts through game tools |

Rules every sub-agent follows:
- It can only call the tools it was granted. Anything else is refused (`Permissions` / `Toolkit.call`).
- A specialist reads every job as its specialty: ask the animator to "design a pricing page" and it still animates.
- Sub-agents cannot create more sub-agents.
- `--deny` / `--allow` adjust the grant; naming a tool in the request ("a helper that can use sqlite") adds it.

## Animations
The animator uses XON's own animation engine (`xon/design/animate.py`), with no model and no network:
- Subjects: ball, square, triangle, star, heart, ring, diamond, text in quotes, loading dots, spinner, stick figure.
- Motions: bounce, jump, spin, pulse/heartbeat, slide, float, orbit, shake, fade, grow, walk, run, wave.
- Colours by name or `#hex`, "on a light background", counts ("three stars"), speed ("slow", "fast", "2 seconds").
- Built-in craft: easing, squash and stretch on impact, contact shadow, staggered groups, a pause button and
  `prefers-reduced-motion`. One motion function drives both the web page and the GIF, so they match.
- Every result is self-checked: does it move, does it loop cleanly, does it stay on stage.
- It refuses copyrighted characters and brand logos; describe an original character instead.
- Limits: it animates simple shapes and stick figures, not drawings or video. Anything outside that list comes back
  as the closest thing it knows.

## Game characters
```bash
xon subagent new "be a shopkeeper in my game named Greta"                    # built-in demo town
xon subagent new "be the shopkeeper of Riverbend" --toolkit game_tools.json  # your game's tools
```
Describe your game's tools in `game_tools.json`; each is an HTTP endpoint on your game server (args arrive as JSON)
or an importable Python function:
```json
{"game": "My RPG",
 "tools": [
  {"name": "shop_inventory", "description": "What the shop sells", "params": {},
   "http": {"url": "http://127.0.0.1:7777/npc/shop_inventory"}},
  {"name": "sell_to_player", "description": "Sell an item to a player",
   "params": {"player": "str", "item": "str", "qty": "int?", "price_each": "int?"},
   "http": {"url": "http://127.0.0.1:7777/npc/sell"}}
 ]}
```
Your game talks to a character through Studio's local API:
`POST http://127.0.0.1:8790/api/subagents/talk` with header `X-XON-Token` and
`{"id": "greta", "player": "Ash", "message": "how much is the sword?"}`.
The shopkeeper lists stock, quotes prices, haggles (counter-offer, then "deal"), buys back and refuses jobs that
are not hers; every price comes from a tool call. `--brain local` lets the local model re-voice her lines (a
rewrite that drops a number is thrown away).

## Local only
`[xon] local_only = true` in `xon.toml` (the default) means XON never calls a cloud model, even if an API key
happens to be set in the environment: the planner is XON's own, chat and coding use the model on this machine,
sub-agents have no cloud brain, and Studio hides the cloud options. The only downloads are free model weights and
open datasets, once, at setup.

Related: [exhort.md](exhort.md), [studio.md](studio.md).
