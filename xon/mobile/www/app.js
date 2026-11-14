import * as Agents from './agents.js';
import * as Anim from './animate.js';

const $ = s => document.querySelector(s);
const store = {get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }};
const MODES = {fast: {max: 192, turns: 2}, balanced: {max: 360, turns: 4}, best: {max: 700, turns: 8}};
const SYSTEM = "You are XON, a small coding assistant running on the user's phone. Be concise. Put code in fenced blocks with a language tag. If unsure, say so.";
let settings = {mode: 'balanced', engine: 'auto', idle: true, ...store.get('xon-settings', {})};

// ------------------------------------------------------------------ model (in a worker)
let worker = null, ready = false, idleTimer = null, nextId = 1;
const pending = new Map();
function llm() {
  if (worker) return worker;
  worker = new Worker('llm-worker.js', {type: 'module'});
  worker.onmessage = ({data: m}) => {
    if (m.type === 'progress' && m.total) { const pct = Math.round(100 * m.loaded / m.total);
      if (m.total > 5e6) { setStatus('busy', `downloading model ${pct}%`); $('#dlbar').hidden = false; $('#dlfill').style.width = pct + '%'; } }
    else if (m.type === 'status') setStatus('busy', m.text);
    else if (m.type === 'ready') { ready = true; $('#dlbar').hidden = true;
      setStatus('on', `ready · ${m.device === 'webgpu' ? 'GPU' : `CPU ×${m.threads}`}`); hw.engine = m.device === 'webgpu' ? 'GPU (WebGPU)' : `CPU, ${m.threads} thread${m.threads > 1 ? 's' : ''}${m.isolated ? '' : ' (single-thread mode)'}`; showHw(); }
    else if (m.type === 'unloaded') { ready = false; setStatus('', 'model asleep (memory freed)'); }
    const p = pending.get(m.id);
    if (!p) { if (m.type === 'error') setStatus('', 'error: ' + m.error); return; }
    if (m.type === 'token') p.onToken(m.text);
    if (m.type === 'done') { pending.delete(m.id); $('#mspeed').textContent = `${m.tps} tokens/s`; hw.last = `${m.tps} tokens/s, first word after ${m.first_token_ms} ms`; showHw(); p.resolve(m); armIdle(); }
    if (m.type === 'error') { pending.delete(m.id); p.reject(new Error(m.error)); }
  };
  return worker;
}
function generate(messages, onToken = () => {}, opts = {}) {
  clearTimeout(idleTimer);
  const id = nextId++, mode = MODES[settings.mode];
  return new Promise((resolve, reject) => {
    pending.set(id, {onToken, resolve, reject});
    if (!ready) setStatus('busy', 'starting model...');
    llm().postMessage({type: 'generate', id, messages, max_new_tokens: opts.max || mode.max, temperature: opts.temperature ?? 0.2, device: settings.engine});
  });
}
function armIdle() { clearTimeout(idleTimer); if (settings.idle) idleTimer = setTimeout(() => worker?.postMessage({type: 'unload'}), 10 * 60 * 1000); }
function setStatus(kind, text) { $('#mdot').className = 'dot ' + kind; $('#mtext').textContent = text; }

// ------------------------------------------------------------------ python (in a worker, with a time limit)
let pyw = null;
function python(code, timeout = 20000) {
  pyw = pyw || new Worker('py-worker.js', {type: 'module'});
  const id = nextId++;
  return new Promise(resolve => {
    const t = setTimeout(() => { pyw.terminate(); pyw = null; resolve({ok: false, output: `stopped after ${timeout / 1000}s (infinite loop?)`}); }, timeout);
    const on = ({data}) => { if (data.id !== id) return; clearTimeout(t); pyw.removeEventListener('message', on); resolve(data); };
    pyw.addEventListener('message', on); pyw.postMessage({id, code});
  });
}

// ------------------------------------------------------------------ rendering
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
function render(text) {
  return text.split('```').map((p, i) => {
    if (i % 2) { const nl = p.indexOf('\n'), lang = (nl > -1 ? p.slice(0, nl) : '').trim(), code = nl > -1 ? p.slice(nl + 1) : p;
      const py = /^(py|python)?$/i.test(lang) && /\b(def|print|import|for|=)\b/.test(code), cpp = /^(cpp|c\+\+|c)$/i.test(lang);
      return `<div class="codebox"><div class="codebar"><span>${esc(lang || 'code')}</span><button data-copy>Copy</button>${py ? '<button data-run>Run</button>' : ''}${cpp ? '<button data-cpp>Run</button>' : ''}</div><pre><code>${esc(code)}</code></pre></div>`; }
    return p.split(/\n{2,}/).map(par => par.trim() ? `<p>${esc(par).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>')}</p>` : '').join('');
  }).join('');
}
document.addEventListener('click', async e => {
  const box = e.target.closest('.codebox'); if (!box) return;
  const code = box.querySelector('code').textContent;
  if (e.target.matches('[data-copy]')) { navigator.clipboard?.writeText(code); e.target.textContent = 'Copied'; }
  const out = () => box.querySelector('.runout') || box.appendChild(Object.assign(document.createElement('div'), {className: 'runout'}));
  if (e.target.matches('[data-cpp]')) { const o = out(); o.className = 'runout'; o.textContent = 'C++ needs a compiler, which phones do not have. Run it in desktop XON (xon studio).'; }
  if (e.target.matches('[data-run]')) {
    e.target.disabled = true; e.target.textContent = 'Running';
    const r = await python(code), o = out(); o.className = 'runout ' + (r.ok ? 'ok' : 'bad'); o.textContent = (r.ok ? '✓ ran\n' : '✗ failed\n') + (r.output || '(no output)');
    e.target.disabled = false; e.target.textContent = 'Run';
  }
});

// ------------------------------------------------------------------ chat
let history = store.get('xon-chat', []);
function addMsg(role, text, meta = '') {
  $('#empty')?.remove();
  const m = document.createElement('div'); m.className = 'msg' + (role === 'user' ? ' me' : '');
  m.innerHTML = `<span class="who">${role === 'user' ? 'You' : 'XON'}</span><div class="bubble">${render(text)}</div>${meta ? `<span class="meta">${esc(meta)}</span>` : ''}`;
  $('#msgs').append(m); m.scrollIntoView({block: 'end'}); return m;
}
history.forEach(h => addMsg(h.role, h.content));
async function send() {
  const text = $('#input').value.trim(); if (!text || $('#send').disabled) return;
  $('#input').value = ''; autosize($('#input'));
  history.push({role: 'user', content: text}); addMsg('user', text);
  const m = addMsg('assistant', '…'), b = m.querySelector('.bubble');
  $('#send').disabled = true; $('#stop').hidden = false;
  let acc = '', last = 0;
  try {
    const turns = MODES[settings.mode].turns * 2;
    const r = await generate([{role: 'system', content: SYSTEM}, ...history.slice(-turns)], t => {
      acc += t; const now = performance.now(); if (now - last > 80) { last = now; b.innerHTML = render(acc); m.scrollIntoView({block: 'end'}); } });
    b.innerHTML = render(acc || '(no answer)'); m.insertAdjacentHTML('beforeend', `<span class="meta">${r.tps} tokens/s · ${r.seconds}s · ${r.device === 'webgpu' ? 'GPU' : 'CPU'}</span>`);
  } catch (err) { b.innerHTML = render(acc + `\n\n⚠ ${err.message}`); }
  if (acc) history.push({role: 'assistant', content: acc});
  history = history.slice(-30); store.set('xon-chat', history);
  $('#send').disabled = false; $('#stop').hidden = true;
}
$('#send').onclick = send;
$('#stop').onclick = () => worker?.postMessage({type: 'stop'});
$('#input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !matchMedia('(pointer: coarse)').matches) { e.preventDefault(); send(); } });
document.querySelectorAll('[data-ex]').forEach(b => b.onclick = () => { $('#input').value = b.dataset.ex; send(); });
function autosize(t) { t.style.height = 'auto'; t.style.height = Math.min(140, t.scrollHeight + 2) + 'px'; }
['#input', '#h-msg'].forEach(s => $(s).addEventListener('input', e => autosize(e.target)));

// ------------------------------------------------------------------ helpers (sub-agents)
let current = null, lastSpec = null;
const CHIPS = {animator: ['a red ball bouncing', 'a stick figure walking', 'a person waving hello on a light background', 'three yellow stars spinning slowly', 'loading dots in purple', "the word 'HI' floating in teal"],
  coder: ['write is_prime(n)', 'write a function that reverses the words in a sentence', 'write fizzbuzz up to 15'],
  shopkeeper: ['what do you sell?', 'how much is the iron sword?', "I'll buy the iron sword for 80 gold", 'deal', 'sell you my iron sword', 'open the gate'],
  guard: ['open the gate because I have a delivery', 'close the gate']};
const ctx = {player: 'Ash', tools: {
  animate: async ({prompt}) => { try { const spec = Anim.parse(prompt); lastSpec = spec; return {ok: true, spec, check: Anim.check(spec)}; } catch (e) { return {ok: false, error: e.message}; } },
  save_gif: async () => saveGif(lastSpec),
  python_run: ({code}) => python(code),
  write_code: async ({task, feedback}) => {
    const fb = feedback ? `\n\nYour last attempt failed with:\n${feedback}\nFix it.` : '';
    const msgs = [{role: 'system', content: 'You are a careful Python engineer.'},
      {role: 'user', content: `Task: ${task}${fb}\n\nReply with exactly two fenced python blocks: first the implementation, then a block of plain assert statements that test it (no pytest, no input()).`}];
    let text = ''; try { await generate(msgs, t => { text += t; }, {max: 500, temperature: feedback ? 0.5 : 0.1}); } catch (e) { return {ok: false, error: e.message}; }
    const blocks = [...text.matchAll(/```(?:python|py)?\n([\s\S]*?)```/g)].map(m => m[1]);
    if (!blocks.length) return {ok: false, error: 'the model did not return code'};
    const code = blocks[0], tests = blocks[1] || (code.includes('assert') ? '' : 'pass');
    return {ok: true, code, tests};
  }}};
function helpersList() {
  const L = Agents.list(); $('#h-list').innerHTML = '';
  L.forEach(a => { const b = document.createElement('button'); b.textContent = `${a.name} · ${a.role}`; b.setAttribute('aria-pressed', String(current?.id === a.id)); b.onclick = () => pick(a); $('#h-list').append(b); });
}
function pick(a) {
  current = a; $('#h-card').hidden = false; $('#h-title').textContent = `${a.name} (${a.role})`;
  $('#h-tools').innerHTML = '<span class="note">can use:</span>' + a.tools.map(t => `<span class="tool">${esc(t)}</span>`).join('');
  $('#h-persona').textContent = a.persona + (a.kind === 'character' ? ' · lives in the demo town' : '');
  $('#h-log').innerHTML = ''; $('#h-msg').placeholder = a.kind === 'character' ? 'say something to ' + a.name : 'give ' + a.name + ' a job';
  $('#h-chips').innerHTML = ''; (CHIPS[a.role] || []).forEach(c => { const b = document.createElement('button'); b.textContent = c; b.onclick = () => helperSay(c); $('#h-chips').append(b); });
  helpersList();
}
function hLine(who, html, me) { const d = document.createElement('div'); d.className = 'msg' + (me ? ' me' : ''); d.innerHTML = `<span class="who">${esc(who)}</span><div class="bubble">${html}</div>`; $('#h-log').append(d); d.scrollIntoView({block: 'end'}); return d; }
async function helperSay(text) {
  if (!current) return; text = text.trim(); if (!text) return;
  $('#h-msg').value = ''; hLine(current.kind === 'character' ? 'Ash' : 'You', esc(text), true);
  const d = hLine(current.name, '…'); $('#h-send').disabled = true;
  const r = await Agents.talk(current, text, ctx);
  const b = d.querySelector('.bubble'); b.innerHTML = render(r.reply || '');
  if (r.spec) { const box = document.createElement('div'); box.style.marginTop = '8px'; box.innerHTML = Anim.svg(r.spec);
    const btn = Object.assign(document.createElement('button'), {textContent: 'Save GIF'}); btn.style.marginTop = '8px';
    const spec = r.spec; btn.onclick = async () => { btn.disabled = true; btn.textContent = 'Making GIF...'; const res = await saveGif(spec); btn.textContent = res.ok ? 'Saved ✓' : 'Save failed'; };
    b.append(box, btn); }
  r.actions.forEach(a => { const res = a.result || {}; d.insertAdjacentHTML('beforeend', `<div class="act">↳ <b>${esc(a.tool)}</b>(${esc(Object.entries(a.args || {}).map(([k, v]) => `${k}=${String(v).slice(0, 40)}`).join(', '))}) ${res.denied ? '<span style="color:var(--bad)">DENIED</span>' : res.ok === false ? '<span style="color:var(--bad)">failed</span>' : '<span style="color:var(--ok)">ok</span>'}</div>`); });
  if (current.role === 'shopkeeper') { const p = Agents.town.state().players.Ash; if (p) d.insertAdjacentHTML('beforeend', `<div class="meta">Ash: ${p.gold} gold · bag: ${Object.entries(p.bag).map(([k, v]) => v + ' ' + k).join(', ') || 'empty'}</div>`); }
  d.scrollIntoView({block: 'end'}); $('#h-send').disabled = false;
}
async function saveGif(spec) {
  if (!spec) return {ok: false, error: 'nothing to save yet'};
  const bytes = await Anim.gif(spec), name = 'xon-' + spec.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40) + '.gif';
  if (window.XONAndroid?.saveFile) {  // the Android app saves straight into Downloads
    let bin = ''; for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return {ok: window.XONAndroid.saveFile(name, btoa(bin), 'image/gif'), file: name};
  }
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(new Blob([bytes], {type: 'image/gif'})), download: name}); a.click();
  return {ok: true, file: name};
}
$('#h-go').onclick = () => { const t = $('#h-task').value.trim(); if (t) pick(Agents.create(t)); };
document.querySelectorAll('[data-h]').forEach(b => b.onclick = () => { $('#h-task').value = b.dataset.h; pick(Agents.create(b.dataset.h)); });
$('#h-send').onclick = () => helperSay($('#h-msg').value);
$('#h-msg').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); helperSay($('#h-msg').value); } });
helpersList();

// ------------------------------------------------------------------ speed settings
const hw = {cores: navigator.hardwareConcurrency || '?', memory: navigator.deviceMemory ? navigator.deviceMemory + ' GB+' : '?', gpu: navigator.gpu ? 'WebGPU available' : 'no WebGPU (CPU mode)',
  threads: crossOriginIsolated ? 'multi-thread ready' : 'single-thread (not isolated)', engine: 'not loaded', last: '-'};
function showHw() { $('#hw').innerHTML = Object.entries({'CPU cores': hw.cores, 'Memory': hw.memory, 'GPU': hw.gpu, 'Threads': hw.threads, 'Engine': hw.engine, 'Last speed': hw.last}).map(([k, v]) => `<span class="note">${k}</span><span>${esc(v)}</span>`).join(''); }
function seg(id, key) { document.querySelectorAll(`#${id} button`).forEach(b => { b.setAttribute('aria-pressed', String(settings[key] === b.dataset.v));
  b.onclick = () => { const changed = settings[key] !== b.dataset.v; settings[key] = b.dataset.v; store.set('xon-settings', settings); seg(id, key);
    if (key === 'engine' && changed && worker) { worker.terminate(); worker = null; ready = false; setStatus('', 'engine changed; reloads on next message'); } }; }); }
seg('mode', 'mode'); seg('engine', 'engine');
$('#idle').checked = settings.idle; $('#idle').onchange = e => { settings.idle = e.target.checked; store.set('xon-settings', settings); armIdle(); };
$('#bench').onclick = async () => { $('#bench').disabled = true; $('#benchout').textContent = 'testing (loads the model first if needed)...';
  try { const r = await generate([{role: 'user', content: 'Count from 1 to 40, separated by spaces.'}], () => {}, {max: 96, temperature: 0});
    $('#benchout').textContent = `${r.tps} tokens/s on ${r.device === 'webgpu' ? 'GPU' : 'CPU'}, first word after ${r.first_token_ms} ms. ` +
      (r.tps < 4 ? 'Slow: use Fast mode, close other apps, keep the phone cool.' : r.tps < 10 ? 'OK: Balanced mode suits this phone.' : 'Fast: Best mode is fine.');
  } catch (e) { $('#benchout').textContent = e.message; }
  $('#bench').disabled = false; };
$('#unload').onclick = () => worker?.postMessage({type: 'unload'});
$('#resettown').onclick = () => Agents.town.reset();
showHw();

// ------------------------------------------------------------------ nav + theme
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x === b ? x.setAttribute('aria-current', 'page') : x.removeAttribute('aria-current'));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('on', v.id === 'v-' + b.dataset.v));
});
try { const t = localStorage.getItem('xon-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
$('#theme').onclick = () => { const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  const nx = cur === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = nx; try { localStorage.setItem('xon-theme', nx); } catch (e) {} };
window.XON = {generate, python, Agents};  // for testing
