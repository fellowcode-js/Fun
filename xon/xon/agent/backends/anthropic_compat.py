"""Anthropic Messages API (or a compatible gateway) with tool use."""
from __future__ import annotations

import json
import os

import requests


class AnthropicBackend:
    name = "anthropic"
    can_plan = True

    def __init__(self):
        self.base = os.environ.get("XON_ANTHROPIC_BASE", "https://api.anthropic.com").rstrip("/")
        self.key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = os.environ.get("XON_ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [m for m in messages if m["role"] != "system"]
        body = {"model": self.model, "max_tokens": 4096, "messages": msgs}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": s["name"], "description": s["description"], "input_schema": {
                "type": "object",
                "properties": {k: {"type": {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array"}
                                   .get(v.rstrip("?"), "string")} for k, v in s["params"].items()},
                "required": [k for k, v in s["params"].items() if not v.endswith("?")]}} for s in tools]
        r = requests.post(f"{self.base}/v1/messages", json=body, timeout=180,
                          headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        content = r.json()["content"]
        text = "".join(c.get("text", "") for c in content if c["type"] == "text")
        calls = [{"id": c["id"], "name": c["name"], "args": c.get("input") or {}} for c in content if c["type"] == "tool_use"]
        return {"content": text, "tool_calls": calls, "raw": {"role": "assistant", "content": content}}

    def tool_result_messages(self, resp: dict, results: list[tuple[dict, dict]]) -> list[dict]:
        return [resp["raw"], {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(r, default=str)[:12000]} for c, r in results]}]
