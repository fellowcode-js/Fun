"""Warm start: an openly licensed pretrained code LM (default Qwen2.5-Coder-0.5B-Instruct, Apache-2.0).

Optional dependency (`pip install xon[pretrained]` = transformers + safetensors). Used for completion, solving,
repair candidates, page generation and the agent's generate -> test -> reflect loop. XON's own from-scratch LM keeps
training in the cycle; this model is evaluated separately and never trained on its own raw output.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
LICENSE = "Apache-2.0"
_CACHE: dict = {}


def available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


class PretrainedCoder:
    def __init__(self, name: str = DEFAULT, cache_dir: str | Path | None = None, threads: int | None = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.name = name
        self.license = LICENSE if name == DEFAULT else "see model card"
        torch.set_num_threads(threads or os.cpu_count() or 4)
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        kw = {"cache_dir": str(cache_dir)} if cache_dir else {}
        self.tok = AutoTokenizer.from_pretrained(name, **kw)
        want = torch.bfloat16 if dev == "cuda" else torch.float32
        import transformers
        major = int(transformers.__version__.split(".")[0])
        dkw = {"dtype": want} if major >= 5 else {"torch_dtype": want}  # kwarg renamed in transformers 5
        self.model = AutoModelForCausalLM.from_pretrained(name, **dkw, **kw).to(dev).eval()
        self.dev = dev

    # ---- raw generation
    def generate(self, prompt: str, max_new: int = 160, n: int = 1, temperature: float = 0.0,
                 stop: tuple[str, ...] = ()) -> list[str]:
        import torch
        ids = self.tok(prompt, return_tensors="pt").to(self.dev)
        sample = temperature > 0 and n > 0
        with torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=max_new, do_sample=sample,
                                      temperature=temperature if sample else None, top_p=0.95 if sample else None,
                                      top_k=None, num_return_sequences=n, pad_token_id=self.tok.eos_token_id,
                                      stop_strings=list(stop) or None, tokenizer=self.tok if stop else None)
        texts = [self.tok.decode(o[ids["input_ids"].shape[1]:], skip_special_tokens=True) for o in out]
        res = []
        for t in texts:
            cut = len(t)
            for s in stop:
                i = t.find(s)
                if i >= 0:
                    cut = min(cut, i)
            res.append(t[:cut])
        return res

    def stream_chat(self, messages: list[dict], max_new: int = 768, temperature: float = 0.3):
        """Yield text pieces as they are generated (for the Studio app)."""
        import threading

        import torch
        from transformers import TextIteratorStreamer
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = self.tok(prompt, return_tensors="pt").to(self.dev)
        streamer = TextIteratorStreamer(self.tok, skip_prompt=True, skip_special_tokens=True)
        kw = dict(**ids, max_new_tokens=max_new, streamer=streamer, pad_token_id=self.tok.eos_token_id,
                  do_sample=temperature > 0, temperature=temperature if temperature > 0 else None, top_p=0.95 if temperature > 0 else None,
                  top_k=None)

        def work():
            with torch.no_grad():
                self.model.generate(**kw)
        t = threading.Thread(target=work, daemon=True)
        t.start()
        for piece in streamer:
            yield piece
        t.join()

    def chat(self, messages: list[dict], max_new: int = 512, temperature: float = 0.0) -> str:
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return self.generate(prompt, max_new=max_new, temperature=temperature)[0]

    # ---- coding
    def solve_python(self, prompt_code: str, n: int = 1, temperature: float = 0.0) -> list[str]:
        bodies = self.generate(prompt_code, max_new=200, n=n, temperature=temperature,
                               stop=("\ndef ", "\nclass ", "\nif __name__", "\n\n\n", "\nprint(", "\nassert "))
        out = []
        for b in bodies:
            lines = []
            for line in b.split("\n"):
                if line and not line.startswith((" ", "\t")) and lines:
                    break
                lines.append(line)
            out.append(prompt_code + "\n".join(lines).rstrip() + "\n")
        return out

    def solve_cpp(self, prompt_code: str, n: int = 1, temperature: float = 0.0) -> list[str]:
        header = "#include <bits/stdc++.h>\nusing namespace std;\n\n"
        bodies = self.generate(header + prompt_code, max_new=220, n=n, temperature=temperature, stop=("\n}\n", "\n}"))
        return [prompt_code + b.rstrip() + "\n}\n" for b in bodies]

    def fill_in_middle(self, prefix: str, suffix: str, max_new: int = 64) -> str:
        return self.generate(f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>", max_new=max_new,
                             stop=("<|endoftext|>", "<|fim_pad|>"))[0]

    def rewrite(self, code: str, error: str, lang: str = "python", tests: str = "", n: int = 1) -> list[str] | str:
        """Repair proposals: reason briefly about the failing check, then rewrite (the caller verifies each)."""
        t = f"\nThe tests that must pass:\n```{lang}\n{tests}\n```\n" if tests else ""
        msg = (f"This {lang} code fails its tests.\n\nCode:\n```{lang}\n{code}\n```\n{t}\nFailure:\n```\n{error[-1200:]}\n```\n"
               "First, in one or two sentences, say which line is wrong and why (compare the expected value with what the "
               "code computes). Then give the corrected code in one fenced block, same function names and signatures.")
        prompt = self.tok.apply_chat_template([{"role": "user", "content": msg}], tokenize=False, add_generation_prompt=True)
        replies = self.generate(prompt, max_new=500, n=1, temperature=0.0)
        if n > 1:
            replies += self.generate(prompt, max_new=500, n=n - 1, temperature=0.8)
        outs = []
        for reply in replies:
            m = re.findall(r"```[a-zA-Z+]*\n(.*?)```", reply, re.S)
            outs.append((m[-1] if m else reply).strip() + "\n")
        return outs if n > 1 else outs[0]

    def write_code(self, task: str, lang: str = "python", feedback: str = "", temperature: float = 0.0) -> dict:
        """Task -> code + tests (one fenced block each). feedback carries the previous attempt's failure."""
        fb = f"\n\nYour previous attempt failed:\n```\n{feedback[-1500:]}\n```\nFix it." if feedback else ""
        tests_hint = ("Then a second ```python block with pytest-style test functions (def test_...) that import nothing "
                      "but assume the functions are defined." if lang == "python" else
                      "Then a second ```cpp block containing only an int main() that checks results and returns 1 on failure.")
        reply = self.chat([{"role": "system", "content": "You are a careful senior engineer. Write small, correct, tested code."},
                           {"role": "user", "content": f"Task: {task}{fb}\n\nFirst a ```{lang} block with the implementation. {tests_hint}"}],
                          max_new=900, temperature=temperature)
        blocks = re.findall(r"```[a-zA-Z+]*\n(.*?)```", reply, re.S)
        return {"code": blocks[0] if blocks else reply, "tests": blocks[1] if len(blocks) > 1 else "", "raw": reply}

    def cpp_tests(self, task: str, code: str) -> str:
        """A focused second call: an int main() with assert checks for the given implementation's functions."""
        sigs = "\n".join(l for l in code.splitlines() if re.match(r"^[\w:<>,\s\*&]+\s+\w+\s*\([^;]*\)\s*\{?\s*$", l) and "main" not in l)
        reply = self.chat([{"role": "user", "content": f"Task: {task}\nFunctions available:\n```cpp\n{sigs}\n```\n"
                            "Write ONLY an `int main()` that checks at least 4 cases (including edge cases) with assert() from <cassert> "
                            "and returns 0. Do not redefine the functions. One ```cpp block."}], max_new=500)
        m = re.findall(r"```[a-zA-Z+]*\n(.*?)```", reply, re.S)
        return m[-1] if m else reply

    def html_page(self, prompt: str) -> str:
        reply = self.chat([{"role": "system", "content": "You are a UI designer who writes clean, accessible HTML and CSS."},
                           {"role": "user", "content": "Write one complete self-contained HTML page (inline <style>, no external assets, "
                            f"no JavaScript frameworks, WCAG AA contrast, lang attribute, labelled inputs) for: {prompt}\n"
                            "Return only the HTML in a ```html block."}], max_new=1000)
        m = re.search(r"```html\n(.*?)```", reply, re.S)
        return (m.group(1) if m else reply).strip()

    def score(self, text: str) -> float:
        """Mean token NLL (lower = more plausible); ranks repair candidates."""
        import torch
        ids = self.tok(text[-3000:], return_tensors="pt").to(self.dev)
        with torch.no_grad():
            return float(self.model(**ids, labels=ids["input_ids"]).loss)


def load(cfg: dict | None = None) -> PretrainedCoder | None:
    """Returns the configured pretrained model, or None when disabled / transformers missing."""
    from xon import config
    cfg = cfg or config.load()
    lm = cfg.get("lm", {})
    if lm.get("init") != "pretrained" or not available():
        return None
    name = lm.get("pretrained", DEFAULT)
    if name not in _CACHE:
        _CACHE[name] = PretrainedCoder(name, cache_dir=config.path(cfg, "checkpoints") / "pretrained")
    return _CACHE[name]
