"""subagent: XON creates its own sub-agents for a task and delegates work to them."""
SPEC = {"name": "subagent", "description": "Create a sub-agent for a kind of work (e.g. 'a helper that makes animations'), "
        "give it a job, or list them. action: create(task) | run(id, message) | list. A sub-agent only gets the XON "
        "tools its specialty needs and works in its own folder.",
        "params": {"action": "str", "task": "str?", "id": "str?", "message": "str?"}}


def run(ctx, action: str, task: str = "", id: str = "", message: str = "", **_) -> dict:
    from xon.agent import subagents as S
    if action == "list":
        return {"ok": True, "agents": S.list_all(ctx.root)}
    if action == "create":
        sa = S.create(task, root=ctx.root)
        return {"ok": True, "agent": sa.spec}
    if action == "run":
        try:
            sa = S.load(id, ctx.root)
        except KeyError:
            names = [a["name"] for a in S.list_all(ctx.root)]
            return {"ok": False, "error": f"no sub-agent called {id}. " + (f"You have: {', '.join(names)}." if names
                                                                             else "Create one first, e.g. 'make a helper that makes animations'.")}
        r = sa.talk(message)
        return {"ok": r.get("ok", True), **r}
    return {"ok": False, "error": f"unknown action {action}"}
