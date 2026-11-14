// Sub-agents on the phone (port of xon/agent/subagents.py): XON picks the role from one line, grants only the tools
// that role needs, and the agent works through those tools. Saved in localStorage.
import * as A from './animate.js';

export const SPECIALISTS = {
  animator: {kw: ['animation', 'animations', 'animate', 'animator', 'gif', 'gifs', 'motion', 'cartoon', 'loop', 'loops'],
    tools: ['animate', 'save_gif'], names: ['Pixel', 'Flip', 'Loop', 'Cel'], persona: 'an animator who turns descriptions into looping animations'},
  // coders are custom specialists now: they use the same XON test-and-fix loop as every other sub-agent
};
export const ROLES = {
  shopkeeper: {kw: ['shopkeeper', 'shop', 'merchant', 'vendor', 'store', 'trader', 'seller', 'market'], names: ['Greta', 'Odo', 'Marla', 'Pim'],
    tools: ['shop_inventory', 'check_price', 'player_wallet', 'sell_to_player', 'buy_from_player', 'shop_restock'],
    persona: 'a friendly but shrewd shopkeeper'},
  guard: {kw: ['guard', 'gate', 'watchman', 'sentry', 'soldier'], names: ['Volk', 'Sera'], tools: ['open_gate', 'close_gate', 'player_wallet'],
    persona: 'a stern town guard'},
};
const GAME = /\b(game|npc|player|rpg|village|town|tavern|quest|shopkeeper|merchant|guard)\b/;
const score = (t, kw) => kw.reduce((n, k) => n + (new RegExp(`(?<![\\w])${k.replace(/[+]/g, '\\+')}(?![\\w])`).test(t) ? 2 : 0), 0);

export function pickRole(task) {
  const t = task.toLowerCase(), game = GAME.test(t);
  let best = null, bs = 0;
  for (const [r, d] of Object.entries(ROLES)) { const s = score(t, d.kw) + (game ? 1 : -1); if (s > bs) [best, bs] = [r, s]; }
  if (best && (game || bs >= 2)) return best;
  let sb = 'custom', ss = 0;
  for (const [r, d] of Object.entries(SPECIALISTS)) { const s = score(t, d.kw); if (s > ss) [sb, ss] = [r, s]; }
  return sb;  // anything else: XON builds a custom specialist for that task
}

// Custom specialist: the specialty comes from the request ("a sub-agent for 3D modeling" -> "3D modeling").
export function specialty(task) {
  let t = task.replace(/\b(?:named|called|name is)\s+[A-Z][\w'-]*/g, ' ').trim();
  t = t.replace(/^(?:please\s+)?(?:make|create|build|spawn|give me|i need|i want)?\s*(?:me\s+)?(?:a|an)?\s*(?:new\s+)?(?:sub-?agent|helper|agent|assistant|bot)?\s*(?:that|who|which|to|for|meant for|made for|focused on|specialized in|good at)?\s*(?:is\s+|does\s+|can\s+|helps?\s+(?:with|me)?\s*)?/i, '');
  return t.replace(/[.!?]+$/, '').trim().slice(0, 60) || 'general tasks';
}
const CUSTOM = {names: ['Nova', 'Atlas', 'Echo', 'Sage', 'Rook', 'Ivy'], tools: ['think', 'write_file', 'read_file', 'python_run']};

export function create(task) {
  const role = pickRole(task), def = SPECIALISTS[role] || ROLES[role] || CUSTOM;
  const named = task.match(/\b(?:named|called|name is)\s+([A-Z][\w'-]*)/);
  let h = 0; for (const c of task) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const name = named ? named[1] : def.names[h % def.names.length];
  const spec = role === 'custom' ? specialty(task) : null;
  const a = {id: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'), name, role: spec ? 'specialist' : role, task, specialty: spec,
    kind: spec ? 'custom' : SPECIALISTS[role] ? 'specialist' : 'character',
    persona: spec ? `${name}, a specialist in ${spec}. Works in its own sandbox and saves what it makes as files.` : `${name}, ${def.persona}`,
    tools: [...def.tools], created: Date.now()};
  const all = list().filter(x => x.id !== a.id); all.push(a); save(all);
  return a;
}
export function list() { try { return JSON.parse(localStorage.getItem('xon-agents') || '[]'); } catch (e) { return []; } }
function save(v) { try { localStorage.setItem('xon-agents', JSON.stringify(v)); } catch (e) {} }
export function remove(id) { save(list().filter(a => a.id !== id)); try { localStorage.removeItem('xon-box-' + id); } catch (e) {} }

// ---------------------------------------------------------------- each custom agent's own sandbox (files only it can touch)
export const sandbox = id => {
  const key = 'xon-box-' + id, get = () => { try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch (e) { return {}; } };
  const put = v => { try { localStorage.setItem(key, JSON.stringify(v)); return true; } catch (e) { return false; } };
  const clean = p => String(p || '').replace(/\\/g, '/').replace(/^\/+|\.\.(\/|$)/g, '').slice(0, 80) || 'out.txt';
  return {files: get,
    write: (path, content) => { const f = get(); f[clean(path)] = String(content).slice(0, 200000); return put(f) ? {ok: true, path: clean(path)} : {ok: false, error: 'sandbox full'}; },
    read: path => { const f = get(), p = clean(path); return p in f ? {ok: true, path: p, content: f[p]} : {ok: false, error: `no file ${p}`}; }};
};

// ---------------------------------------------------------------- demo town (the game the characters live in)
const STOCK = {'iron sword': [120, 3], 'wooden shield': [45, 5], 'health potion': [15, 20], 'mana potion': [18, 12], 'leather boots': [35, 4], torch: [3, 40], rope: [6, 10]};
export const town = (() => {
  let st; try { st = JSON.parse(localStorage.getItem('xon-town')); } catch (e) {}
  st = st || {shop: {gold: 500, stock: Object.fromEntries(Object.entries(STOCK).map(([k, [p, q]]) => [k, {price: p, qty: q}]))}, players: {}, gate: false, log: []};
  const persist = () => { try { localStorage.setItem('xon-town', JSON.stringify(st)); } catch (e) {} };
  const pl = n => st.players[n] ||= {gold: 200, bag: {}};
  const ev = t => { st.log = [...st.log, t].slice(-20); };
  const tools = {
    shop_inventory: () => ({ok: true, items: Object.entries(st.shop.stock).filter(([, v]) => v.qty > 0).map(([k, v]) => ({item: k, ...v}))}),
    check_price: ({item}) => st.shop.stock[item] ? {ok: true, item, ...st.shop.stock[item]} : {ok: false, error: `no ${item}`},
    player_wallet: ({player}) => ({ok: true, ...pl(player)}),
    sell_to_player: ({player, item, qty = 1, price_each}) => {
      const it = st.shop.stock[item], p = pl(player); if (!it || it.qty < qty) return {ok: false, error: `not enough ${item} in stock`};
      const each = price_each ?? it.price; if (each < Math.floor(it.price * 0.7)) return {ok: false, error: 'below the floor price'};
      const total = each * qty; if (p.gold < total) return {ok: false, error: `needs ${total}`, need: total, has: p.gold};
      p.gold -= total; st.shop.gold += total; it.qty -= qty; p.bag[item] = (p.bag[item] || 0) + qty; ev(`${player} bought ${qty} x ${item} for ${total}`); persist();
      return {ok: true, sold: item, qty, total, player_gold: p.gold};
    },
    buy_from_player: ({player, item, qty = 1}) => {
      const p = pl(player); if ((p.bag[item] || 0) < qty) return {ok: false, error: `${player} has no ${item}`};
      const base = st.shop.stock[item]?.price || 10, total = Math.floor(base * 0.5) * qty;
      p.bag[item] -= qty; if (!p.bag[item]) delete p.bag[item]; p.gold += total; st.shop.gold -= total;
      (st.shop.stock[item] ||= {price: base, qty: 0}).qty += qty; ev(`${player} sold ${qty} x ${item} for ${total}`); persist();
      return {ok: true, bought: item, qty, total, player_gold: p.gold};
    },
    shop_restock: ({item, qty = 5}) => { const it = st.shop.stock[item]; if (!it) return {ok: false, error: 'unknown item'}; it.qty += qty; persist(); return {ok: true, item, qty: it.qty}; },
    open_gate: () => { st.gate = true; ev('gate opened'); persist(); return {ok: true}; },
    close_gate: () => { st.gate = false; ev('gate closed'); persist(); return {ok: true}; },
  };
  return {tools, state: () => st, reset() { localStorage.removeItem('xon-town'); location.reload(); }};
})();

// ---------------------------------------------------------------- talking / working
export async function talk(agent, msg, ctx) {
  const actions = [];
  const call = async (tool, args = {}) => {
    let result;
    if (!agent.tools.includes(tool)) result = {ok: false, denied: true, error: `${tool} was not granted to ${agent.name}`};
    else if (town.tools[tool]) result = town.tools[tool](args);
    else if (tool === 'write_file') result = sandbox(agent.id).write(args.path, args.content);
    else if (tool === 'read_file') result = sandbox(agent.id).read(args.path);
    else result = await ctx.tools[tool](args);
    actions.push({tool, args, result}); return result;
  };
  let out;
  if (agent.role === 'animator') out = await animator(agent, msg, call);
  else if (agent.role === 'coder') out = await coder(agent, msg, call, ctx);
  else if (agent.role === 'shopkeeper') out = {reply: await shop(agent, msg, call, ctx.player || 'Ash')};
  else if (agent.role === 'guard') out = {reply: guard(agent, msg, call)};
  else if (agent.kind === 'custom') out = await custom(agent, msg, call, ctx);
  return {...out, actions};
}

async function animator(agent, msg, call) {
  const r = await call('animate', {prompt: msg});
  if (!r.ok) return {reply: r.error};
  const s = r.spec, verbs = {bounce: 'bounces', jump: 'jumps', spin: 'spins', pulse: 'pulses', slide: 'slides', float: 'floats', orbit: 'orbits',
    shake: 'shakes', fade: 'fades', grow: 'grows', walk: 'walks', run: 'runs', wave: 'waves'};
  const subj = {stickman: 'stick figure', dots: 'set of loading dots'}[s.subject] || s.subject;
  const what = s.count > 1 && s.subject !== 'dots' ? `${s.count} ${subj}s that ${s.motions.join(' and ')}` : `a ${subj} that ${s.motions.map(m => verbs[m]).join(' and ')}`;
  return {reply: `Done: ${what}. ${r.check.moves ? 'Checked: it moves' : 'Warning: it barely moves'}${r.check.touchesEdge ? ' (touches the edge)' : ''}. Tap Save GIF to keep it.`, spec: s};
}

async function coder(agent, msg, call, ctx) {
  const block = msg.match(/```(?:py|python)?\n([\s\S]*?)```/);
  if (block) { const r = await call('python_run', {code: block[1]}); return {reply: `${r.ok ? 'It ran fine' : 'It failed'}:\n\`\`\`\n${(r.output || '(no output)').trim().slice(-1500)}\n\`\`\``}; }
  let feedback = '';
  for (let attempt = 1; attempt <= 2; attempt++) {
    const r = await call('write_code', {task: msg, feedback});
    if (!r.ok) return {reply: r.error};
    const run = await call('python_run', {code: r.code + '\n\n' + r.tests + '\nprint("all tests passed")'});
    if (run.ok) return {reply: `Here it is (I ran the tests: they passed${attempt > 1 ? ' on the second try' : ''}):\n\`\`\`python\n${r.code.trim()}\n\`\`\`\nTests:\n\`\`\`python\n${r.tests.trim()}\n\`\`\``};
    feedback = run.output.slice(-800);
    if (attempt === 2) return {reply: `My code still fails its tests, so don't trust it:\n\`\`\`python\n${r.code.trim()}\n\`\`\`\nError:\n\`\`\`\n${feedback.trim()}\n\`\`\``};
  }
}

// Custom specialist: thinks in its role, writes its work into its own sandbox, runs Python it wrote, fixes it once.
// Custom specialist, run on XON's model with XON's thinking loop: do the job in its own sandbox, write files,
// test what it wrote (it adds its own asserts to code), and on failure fix it from the error (up to 3 tries,
// sampling a little more each time). Written to work with the small on-phone model, not only big API models.
const EXT = {python: 'py', py: 'py', obj: 'obj', js: 'js', javascript: 'js', html: 'html', json: 'json', md: 'md', markdown: 'md', svg: 'svg', cpp: 'cpp', 'c++': 'cpp', csv: 'csv', txt: 'txt', text: 'txt', css: 'css', yaml: 'yaml', xml: 'xml'};
const FILE_RX = /FILE:\s*`?([\w./ -]+?)`?\s*\n+```[\w+-]*\n([\s\S]*?)```/g;
function extractFiles(text) {
  const out = [...text.matchAll(FILE_RX)].map(m => [m[1].trim(), m[2]]);
  if (out.length) return out;
  const blocks = [...text.matchAll(/```([\w+-]*)\n([\s\S]*?)```/g)];  // small models often skip the FILE: line
  const py = blocks.filter(b => /^(py|python)?$/i.test(b[1]) && /\b(def|import|print|for|assert|=)\b/.test(b[2]));
  const rest = blocks.filter(b => !py.includes(b)).map((b, i) => [`work-${i + 1}.${EXT[b[1].toLowerCase()] || 'txt'}`, b[2]]);
  return [...(py.length ? [['run.py', py.map(b => b[2]).join('\n\n')]] : []), ...rest];
}
async function custom(agent, msg, call, ctx) {
  const box = sandbox(agent.id), have = Object.keys(box.files());
  const sys = `You are ${agent.name}, an expert in ${agent.specialty}. Do the job yourself.
Put every file you make in a fenced code block, with its name on the line before it, like:
FILE: run.py
\`\`\`python
...
\`\`\`
Use a real file format for the job (3D models: .obj, or a Python script that writes one; notes: .md; code: its language).
If Python can make or check the result, write it as run.py: it will be run. Add assert statements that test your code.
Keep words short. Files already in your sandbox: ${have.join(', ') || 'none'}.`;
  const prior = (agent._hist ||= []).slice(-4);
  let text = '', found = [];
  for (const temperature of [0.2, 0.7]) {  // if no file came back, ask again with a little sampling
    const r = await call('think', {messages: [{role: 'system', content: sys}, ...prior, {role: 'user', content: msg}], temperature});
    if (!r.ok) return {reply: r.error};
    text = r.text; found = extractFiles(text); if (found.length) break;
  }
  const files = [];
  for (const [path, content] of found) { const w = await call('write_file', {path, content}); if (w.ok) files.push(w.path); }
  let ran = '';
  const script = files.find(f => f.endsWith('.py'));
  if (script) {
    let code = box.read(script).content;
    if (/\bdef \w+/.test(code) && !/\bassert\b/.test(code)) {  // code with no checks: XON writes its own tests first
      const t = await call('think', {messages: [{role: 'system', content: 'You write Python tests.'}, {role: 'user', content: `Write 3 to 5 plain assert statements that check this code is correct. Reply with one python block of asserts only.\n\`\`\`python\n${code}\n\`\`\``}], temperature: 0.1});
      const m = t.ok && t.text.match(/```(?:python|py)?\n([\s\S]*?)```/);
      if (m && /\bassert\b/.test(m[1])) { code += '\n\n' + m[1].split('\n').filter(l => /^\s*assert\b/.test(l)).join('\n'); box.write(script, code); }
    }
    for (let attempt = 1; attempt <= 3; attempt++) {
      code = box.read(script).content;
      const res = await call('python_run', {code: SANDBOX_PY(agent.id, box.files(), code) + SANDBOX_SAVE});
      const made = (res.output || '').match(/@@XONFILES@@([\s\S]*)$/);
      if (made) { try { for (const [p, c] of Object.entries(JSON.parse(made[1]))) { const w = box.write(p, c); if (w.ok && !files.includes(w.path)) files.push(w.path); } } catch (e) {} }
      const out = (res.output || '').replace(/@@XONFILES@@[\s\S]*$/, '').trim();
      if (res.ok) { ran = `\n\nI ran ${script}${attempt > 1 ? ` (fixed on try ${attempt})` : ''}${/\bassert\b/.test(code) ? ', its checks pass' : ''}${out ? ':\n```\n' + out.slice(-800) + '\n```' : '.'}`; break; }
      if (attempt === 3) { ran = `\n\n${script} still fails after 3 tries, so don't trust it:\n\`\`\`\n${out.slice(-600)}\n\`\`\``; break; }
      const fix = await call('think', {temperature: attempt === 1 ? 0.3 : 0.6, messages: [{role: 'system', content: sys}, {role: 'user', content:
        `Task: ${msg}\n\nThis ${script} fails:\n\`\`\`python\n${code}\n\`\`\`\nError:\n\`\`\`\n${out.slice(-700)}\n\`\`\`\nFind the bug (one sentence), then reply with the whole fixed script in one python block. Keep the asserts unless an assert itself is wrong.`}]});
      const m = fix.ok && fix.text.match(/```(?:python|py)?\n([\s\S]*?)```/); if (!m) continue;
      box.write(script, m[1]);
    }
  }
  agent._hist = [...prior, {role: 'user', content: msg}, {role: 'assistant', content: text.slice(0, 1500)}];
  const all = list().map(x => x.id === agent.id ? {...x, _hist: agent._hist} : x); save(all);
  let shown = files.length ? text.replace(FILE_RX, (m, name) => `**${name.trim()}** saved to sandbox.`) : text;
  const first = found.find(f => f[0] === script)?.[1];
  if (script && box.read(script).content !== first)  // it changed while testing/fixing: show the final version
    shown = shown.replace(/```[\w+-]*\n[\s\S]*?```/, '').trim() + `\n\nFinal ${script}:\n\`\`\`python\n${box.read(script).content.trim()}\n\`\`\``;
  return {reply: shown + ran, files, ok: !/still fails/.test(ran)};
}
// Python runs inside the agent's sandbox: its files appear as real files, and new/changed ones are copied back.
const SANDBOX_PY = (id, files, code) => `import os, sys, json as _j, shutil as _sh, ast as _ast
_d = '/box/' + ${JSON.stringify(id)}
os.chdir('/'); _sh.rmtree(_d, ignore_errors=True); os.makedirs(_d, exist_ok=True); os.chdir(_d)
for _p, _c in _j.loads(${JSON.stringify(JSON.stringify(files))}).items():
    os.makedirs(os.path.dirname(_p) or '.', exist_ok=True); open(_p, 'w').write(_c)
_before = {p: open(p).read() for p in os.listdir('.') if os.path.isfile(p)}
_src = ${JSON.stringify(JSON.stringify(code))}
_src = _j.loads(_src)
for _n in _ast.walk(_ast.parse(_src)):  # a function that is only a docstring / pass is not done yet
    if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and all(isinstance(b, _ast.Pass) or (isinstance(b, _ast.Expr) and isinstance(getattr(b, 'value', None), _ast.Constant)) for b in _n.body):
        raise NotImplementedError(f"function {_n.name}() has no body yet: write the code inside it")
import unittest as _ut
_um = _ut.main
def _main(*a, **k):  # unittest.main() without killing the run; failures still fail
    k['exit'] = False; k.setdefault('module', _mod); k.setdefault('argv', ['run.py']); r = _um(*a, **k)
    if not r.result.wasSuccessful(): raise AssertionError('unit tests failed')
_ut.main = _main
import types as _ty
_mod = _ty.ModuleType('__main__'); _mod.__file__ = 'run.py'
try:
    exec(compile(_src, 'run.py', 'exec'), _mod.__dict__)
except SystemExit as _e:
    if _e.code not in (0, None): raise
`;
const SANDBOX_SAVE = `\nimport os as _o, json as _j2\n_out = {}\nfor _p in _o.listdir('.'):\n    if _o.path.isfile(_p) and _o.path.getsize(_p) < 200000:\n        try:\n            _c = open(_p).read()\n            if _before.get(_p) != _c: _out[_p] = _c\n        except Exception: pass\nprint('@@XONFILES@@' + _j2.dumps(_out))\n`;

const NUMS = {a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5};
const qty = t => { t = t.replace(/(?:for|at|pay)?\s*\d+\s*(?:gold|g\b|coins?)/g, ' '); const m = t.match(/\b(\d+)\b/); if (m) return +m[1];
  for (const [w, n] of Object.entries(NUMS)) if (new RegExp(`\\b${w}\\b`).test(t)) return n; return 1; };
const offer = t => { const m = t.match(/(?:for|at|offer|pay|give you)\s+(\d+)|(\d+)\s*(?:gold|g\b|coins?)/); return m ? +(m[1] || m[2]) : null; };
const match = (t, items) => items.sort((a, b) => b.length - a.length).find(it => t.includes(it) || t.split(/\W+/).includes(it.split(' ').pop()) || t.includes(it.split(' ').pop() + 's'));

async function shop(agent, msg, call, player) {
  const t = msg.toLowerCase(), mem = agent._pending ||= {};
  const inv = await call('shop_inventory'), items = Object.fromEntries(inv.items.map(i => [i.item, i])), item = match(t, Object.keys(items));
  if (mem[player] && /\b(yes|deal|ok|okay|sure|fine|agreed)\b/.test(t)) {
    const p = mem[player]; delete mem[player];
    const r = await call('sell_to_player', {player, item: p.item, qty: p.qty, price_each: p.each});
    return r.ok ? `Pleasure doing business! ${r.qty} x ${r.sold} for ${r.total} gold. You have ${r.player_gold} left.` : `That won't work: ${r.error}.`;
  }
  if (/\b(sell (you|my)|buy my|want to sell)\b/.test(t)) {
    const w = await call('player_wallet', {player}), it = match(t, Object.keys(w.bag || {}));
    if (!it) return "What are you selling? I don't see it in your bag.";
    const r = await call('buy_from_player', {player, item: it, qty: 1});
    return r.ok ? `I'll take that ${it} for ${r.total} gold. You now have ${r.player_gold}.` : `Can't do that: ${r.error}.`;
  }
  const buy = /\b(buy|purchase|i'?ll take|i want|i'?d like|give me|can i (get|have))\b/.test(t), ask = /\b(how much|price|cost)\b/.test(t);
  if (item && (buy || offer(t) !== null) && !ask) {
    const it = items[item], n = qty(t.replace(item, '')), o = offer(t);
    const each = o === null ? it.price : (n > 1 && o >= it.price * n * 0.5 ? Math.round(o / n) : o);
    if (o !== null && each < it.price * 0.85) { const c = Math.floor(it.price * 0.92); mem[player] = {item, qty: n, each: c};
      return `${each} gold? You wound me. I can do ${c} each for the ${item}, final offer. Deal?`; }
    const r = await call('sell_to_player', {player, item, qty: n, price_each: each});
    if (r.ok) return `Here you go: ${r.qty} x ${r.sold} for ${r.total} gold. You have ${r.player_gold} gold left.`;
    return r.need ? `That's ${r.need} gold and you've only got ${r.has}. Come back with more coin.` : `Sorry, ${r.error}.`;
  }
  if (item && ask) { const r = await call('check_price', {item}); return `The ${item} is ${r.price} gold. I have ${r.qty} in stock.`; }
  if (/\b(what do you (sell|have)|wares|stock|show me|for sale)\b/.test(t) || (buy && !item))
    return `Take a look: ${inv.items.map(i => `${i.item} (${i.price}g)`).join(', ')}.`;
  if (/\b(my gold|how much (gold )?do i have|wallet)\b/.test(t)) { const w = await call('player_wallet', {player}); return `By my count you've got ${w.gold} gold.`; }
  if (/\b(gate|quest)\b/.test(t)) return "That's not my business, friend. Ask the guard. I just run the shop.";
  if (/\b(bye|goodbye|farewell)\b/.test(t)) return 'Safe travels! Come back soon.';
  if (/\b(hi|hello|hey|greetings)\b/.test(t)) return `Welcome to my shop! I'm ${agent.name}. Looking for anything in particular?`;
  return 'Hm? If you want to buy or sell, just say so.';
}

function guard(agent, msg, call) {
  const t = msg.toLowerCase();
  if (/\bopen\b/.test(t)) { if (!/\b(because|for|to)\b/.test(t)) return 'And why should I open the gate? Give me a reason.'; call('open_gate'); return 'Very well. The gate is open. Move along.'; }
  if (/\bclose\b/.test(t)) { call('close_gate'); return "Gate's shut."; }
  return `Halt. I'm ${agent.name} of the town watch. State your business.`;
}

export {A};
