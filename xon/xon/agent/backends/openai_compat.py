"""Any OpenAI-compatible /chat/completions endpoint (OpenAI, vLLM, llama.cpp server, Ollama, ...)."""
from __future__ import annotations

import json
import os

import requests


def _tool_defs(specs: list[dict]) -> list[dict]:
    out = []
    for s in specs:
        props = {k: {"type": {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array"}
                     .get(v.rstrip("?"), "string")} for k, v in s["params"].items()}
        req = [k for k, v in s["params"].items() if not v.endswith("?")]
        out.append({"type": "function", "function": {"name": s["name"], "description": s["description"],
                                                     "parameters": {"type": "object", "properties": props, "required": req}}})
    return out


class OpenAIBackend:
    name = "openai"
    can_plan = True

    def __init__(self):
        self.base = os.environ.get("XON_OPENAI_BASE", "https://api.openai.com/v1").rstrip("/")
        self.key = os.environ.get("XON_OPENAI_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("XON_OPENAI_MODEL", "gpt-4o-mini")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = _tool_defs(tools)
        r = requests.post(f"{self.base}/chat/completions", json=body, timeout=120,
                          headers={"Authorization": f"Bearer {self.key}"})
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        calls = [{"id": c["id"], "name": c["function"]["name"], "args": json.loads(c["function"]["arguments"] or "{}")}
                 for c in msg.get("tool_calls") or []]
        return {"content": msg.get("content") or "", "tool_calls": calls, "raw": msg}

    def tool_result_messages(self, resp: dict, results: list[tuple[dict, dict]]) -> list[dict]:
        out = [resp["raw"]]
        for call, res in results:
            out.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(res, default=str)[:12000]})
        return out
