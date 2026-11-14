"""Small app archetypes the rules planner can build: logic (app.js), designed shell (index.html), tests."""
from __future__ import annotations

TODO_JS = r"""// XON-generated todo app logic. Pure functions are exported for tests; DOM wiring below.
function addItem(items, text) {
  const t = (text || '').trim();
  if (!t) return items;
  return items.concat([{ id: Date.now() + Math.random(), text: t, done: false }]);
}
function removeItem(items, id) { return items.filter(i => i.id !== id); }
function toggleItem(items, id) { return items.map(i => i.id === id ? { ...i, done: !i.done } : i); }
function remaining(items) { return items.filter(i => !i.done).length; }

if (typeof document !== 'undefined') {
  let items = [];
  const $ = s => document.querySelector(s);
  function render() {
    const ul = $('#list');
    ul.innerHTML = '';
    for (const it of items) {
      const li = document.createElement('li');
      li.className = 'item' + (it.done ? ' done' : '');
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = it.done; cb.setAttribute('aria-label', 'done: ' + it.text);
      cb.onchange = () => { items = toggleItem(items, it.id); render(); };
      const span = document.createElement('span'); span.textContent = it.text;
      const del = document.createElement('button');
      del.className = 'del'; del.textContent = '×'; del.setAttribute('aria-label', 'delete ' + it.text);
      del.onclick = () => { items = removeItem(items, it.id); render(); };
      li.append(cb, span, del); ul.append(li);
    }
    $('#count').textContent = remaining(items) + ' left';
  }
  window.addEventListener('DOMContentLoaded', () => {
    $('#add-form').addEventListener('submit', e => {
      e.preventDefault(); items = addItem(items, $('#new').value); $('#new').value = ''; render();
    });
    render();
  });
}
if (typeof module !== 'undefined') module.exports = { addItem, removeItem, toggleItem, remaining };
"""

COUNTER_JS = r"""function step(n, d) { return Math.max(0, n + d); }
if (typeof document !== 'undefined') {
  let n = 0;
  window.addEventListener('DOMContentLoaded', () => {
    const out = document.querySelector('#value');
    document.querySelector('#inc').onclick = () => { n = step(n, 1); out.textContent = n; };
    document.querySelector('#dec').onclick = () => { n = step(n, -1); out.textContent = n; };
  });
}
if (typeof module !== 'undefined') module.exports = { step };
"""


def todo_html(tokens: dict, title: str = "Todo") -> str:
    t = tokens
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>
body{{margin:0;font-family:system-ui,sans-serif;background:{t['bg']};color:{t['text']}}}
header{{background:{t['surface']};padding:14px 24px;border-bottom:1px solid #0001}}
header h1{{margin:0;font-size:22px}}
main{{max-width:520px;margin:24px auto;background:{t['surface']};border-radius:12px;padding:20px;box-shadow:0 1px 4px #0002}}
form{{display:flex;gap:8px}}
#new{{flex:1;padding:10px 12px;border:1px solid {t['muted']};border-radius:8px;font:inherit}}
.add{{background:{t['primary']};color:{t['on-primary']};border:0;border-radius:8px;padding:10px 16px;font:600 15px system-ui}}
ul{{list-style:none;padding:0;margin:16px 0 0}}
.item{{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #0001}}
.item span{{flex:1}}
.item.done span{{text-decoration:line-through;color:{t['muted']}}}
.del{{background:transparent;border:0;color:#b8b8b8;font-size:14px;width:18px;height:18px;padding:0}}
#count{{margin-top:12px;color:#9a9a9a;font-size:13px}}
</style></head>
<body>
<header><h1>{title}</h1></header>
<main>
  <form id="add-form"><input id="new" placeholder="What needs doing?"><button class="add" type="submit">Add</button></form>
  <ul id="list"></ul>
  <p id="count"></p>
</main>
<script src="app.js"></script>
</body></html>
"""


TODO_TEST = r'''"""XON-generated tests for the todo app: logic via node (if present) and real clicks in headless Chromium."""
import json
import pathlib
import shutil
import subprocess

import pytest

HERE = pathlib.Path(__file__).parent


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_logic_node():
    js = ("const a=require('./app.js');let x=a.addItem([], ' milk ');x=a.addItem(x,'');x=a.addItem(x,'eggs');"
          "const id=x[0].id;const y=a.toggleItem(x,id);"
          "console.log(JSON.stringify({n:x.length,first:x[0].text,rem:a.remaining(y),after:a.removeItem(x,id).length}))")
    out = subprocess.run(["node", "-e", js], cwd=HERE, capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    assert r == {"n": 2, "first": "milk", "rem": 1, "after": 1}


def _browser():
    try:
        from xon.design.render import Renderer
        return Renderer
    except Exception:
        return None


def test_ui_add_and_delete():
    R = _browser()
    if R is None:
        pytest.skip("no headless browser")
    try:
        r = R().__enter__()
    except Exception as e:
        pytest.skip(f"no headless browser: {e}")
    try:
        page = r._page
        page.goto((HERE / "index.html").as_uri())
        for t in ["milk", "eggs", "  "]:
            page.fill("#new", t)
            page.click("button.add")
        assert page.locator("#list li").count() == 2
        assert page.inner_text("#count") == "2 left"
        page.click("#list li >> nth=0 >> button.del")
        assert page.locator("#list li").count() == 1
        page.check("#list li >> nth=0 >> input[type=checkbox]")
        assert page.inner_text("#count") == "0 left"
    finally:
        r.__exit__(None, None, None)


def test_dom_structure():
    html = (HERE / "index.html").read_text()
    for needle in ['id="new"', 'id="list"', 'id="count"', 'src="app.js"', "<h1"]:
        assert needle in html
'''

ARCHETYPES = {
    "todo": {"files": {"app.js": TODO_JS, "test_app.py": TODO_TEST}, "html": todo_html, "title": "Todo"},
}


def pick(task: str) -> str:
    t = task.lower()
    if any(w in t for w in ("todo", "to-do", "task list", "checklist", "shopping list")):
        return "todo"
    return "todo"
