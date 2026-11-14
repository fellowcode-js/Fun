"""`xon` command line: workstation, nodes, training, design tools and the agent."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def _cfg(root=None):
    from xon import config
    return config.load(Path(root) if root else None)


def _print(x):
    print(json.dumps(x, indent=1, default=str))


def cmd_init(a):
    from xon import config
    from xon.workstation import bootstrap
    root = config.find_root()
    hw = bootstrap.init(root, a.budget, a.gpu_price, a.tier, live=False if a.offline else None, bench_steps=a.bench_steps)
    if not hw["plan"]["fits"]:
        return 2
    return 0


def cmd_doctor(a):
    from xon.workstation import doctor
    return doctor.run(check_network=not a.offline)


def cmd_stop(a):
    from xon.workstation.governor import Governor
    Governor(_cfg()).stop(a.reason)
    print("XON: STOP file written; all nodes halt within seconds. `xon resume` clears it.")


def cmd_resume(a):
    from xon.workstation.governor import Governor
    Governor(_cfg()).clear_stop()
    print("XON: STOP cleared.")


def cmd_status(a):
    from xon.workstation.dashboard.server import gather
    d = gather(_cfg())
    _print({"tier": d["tier"], "governor": d["governor"], "nodes": d["nodes"], "kinds": d["kinds"],
            "cycles": [{k: h[k] for k in ("cycle", "promoted", "reason")} for h in d["history"]],
            "promoted": d["promoted"], "phase": d["status"].get("phase")})


def cmd_crawl(a):
    from xon.nodes.crawler_node import crawl_once
    cfg = _cfg()
    mock = True if a.mock else False if a.live else not cfg["crawler"].get("live", False)
    _print(crawl_once(cfg, mock=mock, max_pages=a.max_pages, open_data=not a.no_open))


def cmd_train(a):
    from xon.nodes.trainer_node import run
    out = run(_cfg(), cycles=a.cycles, wait_for_data_s=5, quick=a.quick)
    _print([{k: r[k] for k in ("cycle", "promoted", "reason", "metrics", "minutes")} for r in out])


def cmd_eval(a):
    from xon import config
    from xon.tokenizer import BPETokenizer
    from xon.trainer.cycle import Cycle
    cfg = _cfg()
    p = config.path(cfg, "checkpoints") / "promoted"
    c = Cycle(cfg, quick=a.quick)
    m = c.evaluate(p / "lm.pt", p / "vision.pt", BPETokenizer.load(p / "tokenizer.json"))
    m.pop("_detail")
    _print(m)


def _start_proc(args: list[str], log: Path) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([sys.executable, "-m", "xon.agent.cli", *args], stdout=open(log, "a"), stderr=subprocess.STDOUT,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})


def cmd_start(a):
    from xon import config
    from xon.nodes.common import heartbeat
    from xon.workstation.governor import Governor
    cfg = _cfg()
    root = Path(cfg["_root"])
    if not (root / "xon.toml").exists():
        print("XON: no xon.toml yet, running `xon init` first")
        cmd_init(argparse.Namespace(budget=None, gpu_price=0.0, tier=None, offline=False, bench_steps=60))
        cfg = _cfg()
    logs = config.path(cfg, "logs")
    gov = Governor(cfg, "agent")
    if a.node == "crawler":
        from xon.nodes.crawler_node import run_forever
        run_forever(cfg, interval_s=a.interval, mock=True if a.mock else None)
        return 0
    if a.node == "trainer":
        from xon.nodes.trainer_node import run
        run(cfg, cycles=a.cycles, quick=a.quick)
        return 0
    # --all or --node agent: the agent node supervises the others and serves the dashboard
    from xon.workstation.dashboard.server import serve
    srv = serve(cfg, port=a.port, background=True)
    print(f"XON dashboard: http://127.0.0.1:{srv.server_address[1]}/")
    procs = {}
    if a.all:
        crawl_args = ["start", "--node", "crawler", "--interval", str(a.interval)] + (["--mock"] if a.mock else [])
        procs["crawler"] = _start_proc(crawl_args, logs / "crawler_node.log")
        # let the crawler finish its first round so the trainer sees fresh shards
        hb = config.path(cfg, "exchange") / "heartbeats" / "crawler.json"
        t_wait = time.time()
        while time.time() - t_wait < 900 and procs["crawler"].poll() is None and not gov.stopped():
            try:
                if json.loads(hb.read_text()).get("phase") in ("sleep", "halted") and hb.stat().st_mtime > t_wait:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        procs["trainer"] = _start_proc(["start", "--node", "trainer", "--cycles", str(a.cycles)] + (["--quick"] if a.quick else []),
                                       logs / "trainer_node.log")
    print(f"XON nodes started: {', '.join(procs) or 'agent only'} (logs in {logs}). `xon stop` or the STOP button halts all.")
    try:
        while True:
            heartbeat(cfg, "agent", phase="supervising", children={k: p.pid for k, p in procs.items()})
            if gov.stopped():
                print("XON: STOP detected, terminating nodes")
                break
            if procs and all(p.poll() is not None for p in procs.values()) and not a.keep_alive:
                print("XON: all nodes finished")
                break
            if "trainer" in procs and procs["trainer"].poll() is not None and not a.keep_alive:
                print("XON: trainer finished its cycles; stopping (use --keep-alive to keep crawling)")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    for p in procs.values():
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
    for p in procs.values():
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
    heartbeat(cfg, "agent", phase="stopped")
    return 0


def cmd_design(a):
    from xon.agent.tools import Context, registry
    cfg = _cfg()
    ctx = Context(Path.cwd().resolve(), cfg)
    t = registry()["design"]
    kw = {"prompt": a.prompt or "", "path": a.path or "", "out": a.out or "", "base": a.base, "dark": a.dark, "ratio": a.ratio}
    r = t.run(ctx, a.action, **kw)
    _print(r)
    return 0 if r.get("ok") else 1


def cmd_agent(a):
    from xon.agent.loop import Agent
    root = Path(a.root).resolve() if a.root else Path.cwd().resolve()
    ag = Agent(root, mode=a.mode, backend=a.backend, assume_yes=a.yes, allow_protected=a.allow_protected, max_steps=a.max_steps)
    r = ag.run(a.task, a.workspace)
    _print({k: v for k, v in r.items() if k != "diff"})
    if r.get("diff"):
        print(r["diff"])
    return 0 if not r.get("error") and not r.get("stopped") else 1


def cmd_agents(a):
    from xon.agent import manager
    _print(manager.agents(Path.cwd()))


def cmd_spawn(a):
    from xon.agent import manager
    _print(manager.spawn(Path.cwd(), a.task, mode=a.mode, wait=a.wait))


def cmd_collect(a):
    from xon.agent import manager
    _print(manager.collect(Path.cwd(), a.ids or None))


def cmd_dashboard(a):
    from xon.workstation.dashboard.server import serve
    serve(_cfg(), port=a.port)


def cmd_complete(a):
    from xon.agent.tools import Context, registry
    _print(registry()["complete"].run(Context(Path.cwd(), _cfg()), a.prefix, a.suffix or "", a.max_new))


def cmd_gate(a):
    from xon import gates
    r = gates.run(a.name, _cfg(), quick=a.quick)
    _print(r)
    return 0 if r.get("pass") else 1


def cmd_report(a):
    from xon import report
    p = report.write(_cfg())
    print(f"wrote {p}")


def cmd_studio(a):
    from xon.studio.server import serve
    serve(_cfg(), port=a.port, token=a.token, open_browser=a.open)


def cmd_mcp(a):
    from xon.studio.mcp_server import main as mcp_main
    if a.root:
        os.environ["XON_HOME"] = str(Path(a.root).resolve())
    mcp_main(a.root)


def cmd_debug_bundle(a):
    from xon.studio.debug import bundle
    print(f"XON debug bundle: {bundle(_cfg(), out=Path(a.out) if a.out else None)}")


def cmd_repl(a):
    from xon.agent.commands import dispatch
    from xon.agent.loop import Agent
    cfg = _cfg()
    root = Path.cwd().resolve()
    st = {"root": root, "cfg": cfg, "agent": Agent(root, cfg, mode=a.mode), "workspace": "."}
    print(BISCUIT)
    print("XON agent with Biscuit. /help for commands, /quit to exit.")
    while True:
        try:
            line = input("xon> ")
        except EOFError:
            break
        if not dispatch(st, line):
            break


def cmd_exhort(a):
    from xon.exhort import exhort_promoted
    ov = {k: v for k, v in {"heal_steps": a.heal_steps, "max_frac": a.max_frac}.items() if v is not None}
    r = exhort_promoted(_cfg(), dry_run=a.dry_run, apply=a.apply, checkpoint=a.checkpoint, overrides=ov)
    if r.get("ok"):
        print(f"Exhort: {r['neurons']} neurons checked -> {r['broken']} broken, {r['dead']} dead, {r['useless']} useless")
        for L in r["layers"]:
            if L["targets"]:
                print(f"  {L['name']:<16} {len(L['targets']):>3}/{L['size']}  broken {L['broken'][:8]} dead {L['dead'][:8]} useless {L['useless'][:8]}")
        print(f"  reborn {r['reborn']}  kept={r['kept']}  ({r['reason']})" + (f"\n  applied to {r['applied']}" if r.get("applied") else ""))
        return 0
    _print(r)
    return 1


def cmd_subagent(a):
    from xon.agent import subagents as S
    from xon import config
    root = Path(a.root).resolve() if getattr(a, "root", None) else config.find_root()
    if a.action == "new":
        split = lambda v: [x.strip() for x in (v or "").split(",") if x.strip()]
        sa = S.create(" ".join(a.args), a.toolkit, name=a.name, role=a.role, allow=split(a.allow), deny=split(a.deny),
                      brain=a.brain, root=root)
        _print(sa.spec)
        print(f"\nTalk to it:  xon subagent talk {sa.spec['id']}")
    elif a.action == "list":
        for s in S.list_all(root):
            print(f"{s['id']:<18} {s['role']:<11} {s['brain']:<6} tools: {', '.join(s['tools']) or '(none)'}")
    elif a.action == "show":
        _print(S.load(a.args[0], root).spec)
    elif a.action == "rm":
        print("removed" if S.remove(a.args[0], root) else "no such sub-agent")
    elif a.action == "talk":
        sa = S.load(a.args[0], root)
        line = " ".join(a.args[1:])
        def say(msg):
            r = sa.talk(msg, player=a.player, brain=a.brain if a.brain != "auto" else None)
            for act in r["actions"]:
                res = act["result"]
                mark = "DENIED" if res.get("denied") else ("ok" if res.get("ok", True) else "fail")
                print(f"   [{act['tool']}({', '.join(f'{k}={v}' for k, v in act['args'].items())}) -> {mark}]")
            print(f"{sa.name}: {r['reply']}")
        if line:
            say(line)
            return 0
        print(f"Talking to {sa.name} ({sa.spec['role']}, brain {sa.brain()}). Empty line or Ctrl+D to leave.")
        while True:
            try:
                msg = input(f"{a.player}> ").strip()
            except EOFError:
                break
            if not msg:
                break
            say(msg)
    return 0


BISCUIT = r"""
   /\_/\     Biscuit (XON's cat)
  ( o.o )    brown & white, mostly napping,
   > ^ <     occasionally fixing your tests
  /|_X_|\
"""


def main(argv=None):
    p = argparse.ArgumentParser(prog="xon", description="XON (X-87, X-Over-Node): coding + design workstation")
    sp = p.add_subparsers(dest="cmd")
    s = sp.add_parser("init", help="probe hardware, pick tier, size the run, write xon.toml")
    s.add_argument("--budget", default=None, help="e.g. 30m, 8h, 2d or $40 (with --gpu-price)")
    s.add_argument("--gpu-price", type=float, default=0.0)
    s.add_argument("--tier", choices=["A", "B", "C"])
    s.add_argument("--offline", action="store_true")
    s.add_argument("--bench-steps", type=int, default=100)
    s.set_defaults(fn=cmd_init)
    s = sp.add_parser("doctor", help="check the workstation and print fixes")
    s.add_argument("--offline", action="store_true")
    s.set_defaults(fn=cmd_doctor)
    s = sp.add_parser("start", help="start nodes (--all, or --node crawler|trainer|agent)")
    s.add_argument("--all", action="store_true")
    s.add_argument("--node", choices=["crawler", "trainer", "agent"], default="agent")
    s.add_argument("--cycles", type=int, default=1)
    s.add_argument("--mock", action="store_true")
    s.add_argument("--quick", action="store_true")
    s.add_argument("--interval", type=float, default=600)
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--keep-alive", action="store_true")
    s.set_defaults(fn=cmd_start)
    s = sp.add_parser("stop", help="kill switch: halt every node within seconds")
    s.add_argument("--reason", default="xon stop")
    s.set_defaults(fn=cmd_stop)
    sp.add_parser("resume", help="clear the STOP file").set_defaults(fn=cmd_resume)
    sp.add_parser("status", help="governor, nodes, cycles").set_defaults(fn=cmd_status)
    s = sp.add_parser("crawl", help="one crawl round (+clean, shard, push)")
    s.add_argument("--mock", action="store_true")
    s.add_argument("--live", action="store_true")
    s.add_argument("--max-pages", type=int)
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(fn=cmd_crawl)
    s = sp.add_parser("train", help="run learning cycle(s)")
    s.add_argument("--cycles", type=int, default=1)
    s.add_argument("--quick", action="store_true")
    s.set_defaults(fn=cmd_train)
    s = sp.add_parser("eval", help="evaluate promoted checkpoints on frozen sets")
    s.add_argument("--quick", action="store_true")
    s.set_defaults(fn=cmd_eval)
    s = sp.add_parser("design", help="design tools")
    s.add_argument("action", choices=["from_prompt", "from_screenshot", "critique", "palette", "type", "tokens"])
    s.add_argument("--prompt")
    s.add_argument("--path")
    s.add_argument("--out")
    s.add_argument("--base", default="#2f5fd0")
    s.add_argument("--dark", action="store_true")
    s.add_argument("--ratio", type=float, default=1.25)
    s.set_defaults(fn=cmd_design)
    s = sp.add_parser("agent", help="run the agent on a task")
    s.add_argument("task")
    s.add_argument("--mode", choices=["ask", "auto-edit", "full-auto"])
    s.add_argument("--backend")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--allow-protected", action="store_true")
    s.add_argument("--root")
    s.add_argument("--workspace", default=".")
    s.add_argument("--max-steps", type=int)
    s.set_defaults(fn=cmd_agent)
    sp.add_parser("agents", help="list parallel agents").set_defaults(fn=cmd_agents)
    s = sp.add_parser("spawn", help="run a task in an isolated worktree")
    s.add_argument("task")
    s.add_argument("--mode", default="auto-edit")
    s.add_argument("--wait", action="store_true")
    s.set_defaults(fn=cmd_spawn)
    s = sp.add_parser("collect", help="merge finished agent branches; flag conflicts")
    s.add_argument("ids", nargs="*")
    s.set_defaults(fn=cmd_collect)
    s = sp.add_parser("dashboard", help="serve the dashboard")
    s.add_argument("--port", type=int, default=8787)
    s.set_defaults(fn=cmd_dashboard)
    s = sp.add_parser("complete", help="XON LM completion / fill-in-the-middle")
    s.add_argument("prefix")
    s.add_argument("--suffix")
    s.add_argument("--max-new", type=int, default=64)
    s.set_defaults(fn=cmd_complete)
    s = sp.add_parser("gate", help="run a milestone gate check (m0..m4)")
    s.add_argument("name", choices=["m0", "m1", "m2", "m3", "m4"])
    s.add_argument("--quick", action="store_true")
    s.set_defaults(fn=cmd_gate)
    sp.add_parser("report", help="regenerate the expectations table in REPORT.md").set_defaults(fn=cmd_report)
    s = sp.add_parser("studio", help="XON Studio: local app (chat, code, design, fix, agent) + cloud bridge")
    s.add_argument("--port", type=int, default=8790)
    s.add_argument("--token", help="fixed access token (default: random per run)")
    s.add_argument("--open", action="store_true", help="open the browser")
    s.set_defaults(fn=cmd_studio)
    s = sp.add_parser("mcp", help="MCP server on stdio for Claude Code / Claude Desktop")
    s.add_argument("--root", help="XON root (default: auto-detect)")
    s.set_defaults(fn=cmd_mcp)
    s = sp.add_parser("debug-bundle", help="write a scrubbed debug zip")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_debug_bundle)
    s = sp.add_parser("repl", help="interactive agent with slash commands")
    s.add_argument("--mode", default="ask")
    s.set_defaults(fn=cmd_repl)
    s = sp.add_parser("exhort", help="find dead/broken/useless neurons in the XON LM and reincarnate them better")
    s.add_argument("--dry-run", action="store_true", help="only diagnose")
    s.add_argument("--apply", action="store_true", help="replace the promoted LM if Exhort kept the result")
    s.add_argument("--checkpoint", help="a specific LM checkpoint instead of the promoted one")
    s.add_argument("--heal-steps", type=int)
    s.add_argument("--max-frac", type=float)
    s.set_defaults(fn=cmd_exhort)
    s = sp.add_parser("subagent", help="spawn role sub-agents (NPCs) with game tools: new | list | show | talk | rm")
    s.add_argument("action", choices=["new", "list", "show", "talk", "rm"])
    s.add_argument("args", nargs="*", help="new: the task text; talk: ID [message]; show/rm: ID")
    s.add_argument("--toolkit", help="demo (built-in town), code, or a game_tools.json path")
    s.add_argument("--name")
    s.add_argument("--role", help="force a role: " + "shopkeeper, blacksmith, innkeeper, guard, questgiver, coder, npc")
    s.add_argument("--allow", help="extra tools to grant, comma separated")
    s.add_argument("--deny", help="tools to withhold, comma separated")
    s.add_argument("--brain", default="auto", choices=["auto", "rules", "local", "cloud"])
    s.add_argument("--player", default="player")
    s.add_argument("--root")
    s.set_defaults(fn=cmd_subagent)
    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        p.print_help()
        return 0
    try:
        return a.fn(a) or 0
    except ModuleNotFoundError as e:
        print(f"XON: missing dependency {e.name}. Fix: pip install -e .  (or run scripts/setup.sh)", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
