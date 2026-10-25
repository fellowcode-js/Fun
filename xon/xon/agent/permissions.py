"""Permission modes: ask (default), auto-edit, full-auto. Protected paths always need explicit approval."""
from __future__ import annotations

import sys

READ_ONLY = {"read", "glob", "grep", "view_image", "recognize", "complete", "test", "git_status", "git_diff", "design_read"}
EDITS = {"write", "edit"}
PROTECTED = ("evalsets/", "xon/workstation/governor.py", "xon/pipeline/clean_text.py", "xon/pipeline/clean_images.py",
             "xon/design/brand.py", "xon/agent/sandbox.py", "xon/agent/permissions.py")


class PermissionDenied(PermissionError):
    pass


class Permissions:
    def __init__(self, mode: str = "ask", allow_protected: bool = False, interactive: bool | None = None,
                 allowlist: list[str] | None = None, assume_yes: bool = False):
        assert mode in ("ask", "auto-edit", "full-auto"), mode
        self.mode = mode
        self.allow_protected = allow_protected
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.allowlist = set(allowlist or [])
        self.assume_yes = assume_yes

    def _ask(self, what: str) -> bool:
        if self.assume_yes:
            return True
        if not self.interactive:
            return False
        ans = input(f"XON wants to {what}. Allow? [y/N] ").strip().lower()
        return ans in ("y", "yes")

    def check(self, tool: str, args: dict) -> None:
        if self.allowlist and tool not in self.allowlist:
            raise PermissionDenied(f"tool {tool!r} not in xon.toml agent.tool_allowlist")
        path = str(args.get("path", ""))
        if tool in EDITS and any(path.startswith(p) or path == p.rstrip("/") for p in PROTECTED):
            if not self.allow_protected:
                raise PermissionDenied(f"{path} is protected (eval sets, governor, safety filters); "
                                       "re-run with --allow-protected after review")
        if tool in READ_ONLY:
            return
        if tool in EDITS and self.mode in ("auto-edit", "full-auto"):
            return
        if self.mode == "full-auto":
            return
        desc = f"run {tool} {args.get('cmd') or args.get('path') or args.get('url') or ''}".strip()
        if not self._ask(desc):
            raise PermissionDenied(f"{tool} needs approval in '{self.mode}' mode (use --mode auto-edit/full-auto or --yes)")
