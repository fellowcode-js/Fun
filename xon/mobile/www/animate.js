// XON animation engine (port of xon/design/animate.py): description -> looping SVG animation + GIF frames.
// Same motion model as the desktop version, so results match. Runs entirely on the phone.
export const COLORS = {red: '#e5484d', orange: '#f76b15', yellow: '#ffc53d', gold: '#e2a336', green: '#30a46c', lime: '#99d52a',
  teal: '#12a594', cyan: '#00a2c7', blue: '#3e63dd', navy: '#1e3a8a', purple: '#8e4ec6', violet: '#6e56cf', pink: '#e93d82',
  magenta: '#d6409f', brown: '#a0612b', black: '#1c1c1c', white: '#f5f5f5', gray: '#8b8d98', grey: '#8b8d98', silver: '#c1c4cc'};
const SUBJECTS = [
  ['stickman', 'stick ?(?:figure|man|person)|stickman|person|man|woman|character|guy|kid|human'],
  ['dots', 'loading dots|dots|loader|typing indicator'], ['spinner', 'spinner|loading (?:circle|ring|wheel)|throbber'],
  ['heart', 'hearts?'], ['star', 'stars?'], ['square', 'squares?|box(?:es)?|cubes?|blocks?'], ['triangle', 'triangles?'],
  ['diamond', 'diamonds?|gems?'], ['ring', 'rings?|donuts?|circle outline'], ['ball', 'balls?|circles?|orbs?|bubbles?|planets?|dots?']];
const MOTIONS = {bounce: 'bounc\\w*|bouncy', jump: 'jump\\w*|hop\\w*', spin: 'spin\\w*|rotat\\w*|twirl\\w*|turn\\w*',
  pulse: 'puls\\w*|heartbeat|beat\\w*|throb\\w*|breath\\w*', slide: 'slid\\w*|mov\\w* (?:left|right|across|side)|swing\\w*|sway\\w*',
  float: 'float\\w*|hover\\w*|bob\\w*|drift\\w*', orbit: 'orbit\\w*|circl\\w* around|go\\w* around',
  shake: 'shak\\w*|wiggl\\w*|jiggl\\w*|vibrat\\w*|wobbl\\w*', fade: 'fad\\w*|blink\\w*|flash\\w*|glow\\w*',
  grow: 'grow\\w*|shrink\\w*|zoom\\w*|scal\\w*', walk: 'walk\\w*|stroll\\w*|march\\w*', run: 'run\\w*|sprint\\w*|jog\\w*',
  wave: 'wav(?:e|es|ing)(?: hello| hi| goodbye)?|hello|greet\\w*'};
const DEFAULT_MOTION = {ball: ['bounce'], stickman: ['walk'], dots: ['pulse'], spinner: ['spin'], heart: ['pulse'], star: ['spin', 'pulse'],
  text: ['float'], square: ['spin'], triangle: ['spin'], diamond: ['float', 'spin'], ring: ['pulse']};
const WORDNUM = {two: 2, three: 3, four: 4, five: 5, six: 6, 'a couple of': 2, several: 4, many: 6};
const BLOCKED = /\b(mickey|mario|pikachu|sonic|spongebob|homer simpson|elsa|batman|spider-?man|superman|minion|disney|nintendo|pokemon)\b/i;

export function parse(prompt) {
  if (BLOCKED.test(prompt)) throw new Error("I won't animate a copyrighted character. Describe an original one instead (for example 'a stick figure in a red cap waving').");
  const p = prompt.toLowerCase();
  const s = {subject: 'ball', motions: [], color: '#3e63dd', background: '#14151a', count: 1, duration: 1.6, text: '', width: 480, height: 320, title: prompt.trim().slice(0, 80) || 'Animation'};
  const q = prompt.match(/["“']([^"”']{1,40})["”']/);
  if (q && /\b(text|word|title|says?|saying|letters?)\b/.test(p)) { s.subject = 'text'; s.text = q[1]; }
  else {
    const hits = [];
    for (const [name, rx] of SUBJECTS) { const m = p.match(new RegExp(`\\b(?:${rx})\\b`)); if (m) hits.push([m.index, name]); }
    if (hits.length) {
      hits.sort((a, b) => a[0] - b[0]);
      s.subject = hits.some(h => h[1] === 'stickman') ? 'stickman' : hits[0][1];
      if (hits.some(h => h[1] === 'dots') && /loading|loader|typing/.test(p)) s.subject = 'dots';
    }
  }
  s.motions = Object.keys(MOTIONS).filter(m => new RegExp(`\\b(?:${MOTIONS[m]})`).test(p));
  if (s.subject !== 'stickman') {
    const only = s.motions.filter(m => !['walk', 'run', 'wave'].includes(m));
    if (only.length) s.motions = only; else if (s.motions.length) s.motions = s.motions.includes('wave') ? ['float'] : ['slide'];
  }
  if (!s.motions.length) s.motions = [...DEFAULT_MOTION[s.subject]];
  if (s.motions.includes('bounce') && s.motions.includes('jump')) s.motions = s.motions.filter(m => m !== 'jump');
  const hex = prompt.match(/#[0-9a-fA-F]{6}\b/);
  let best = null;
  for (const c of Object.keys(COLORS)) { const m = p.match(new RegExp(`\\b${c}\\b`)); if (m && (!best || m.index < best[0])) best = [m.index, c]; }
  if (hex) s.color = hex[0]; else if (best) s.color = COLORS[best[1]];
  const bg = p.match(new RegExp(`\\bon (?:a |an )?(${Object.keys(COLORS).join('|')}|light|dark) (?:background|bg|sky|backdrop)`));
  if (bg) s.background = {light: '#f4f2ee', dark: '#14151a'}[bg[1]] || COLORS[bg[1]] || '#14151a';
  else if (/\b(light|white) (background|bg|theme)\b/.test(p)) s.background = '#f4f2ee';
  const n = p.match(new RegExp(`\\b(\\d+)\\s+(?:\\w+\\s+)?(?:${SUBJECTS.map(x => x[1]).join('|')})`));
  if (n) s.count = +n[1]; else for (const [w, v] of Object.entries(WORDNUM)) if (new RegExp(`\\b${w}\\b`).test(p)) s.count = v;
  if (s.subject === 'dots' && !n) s.count = 3;
  s.count = Math.max(1, Math.min(s.count, s.subject === 'stickman' ? 3 : 8));
  const secs = p.match(/(\d+(?:\.\d+)?)\s*(?:s\b|sec|second)/);
  if (secs) s.duration = +secs[1];
  else if (/\b(very fast|super fast|quick(ly)?|fast|rapid)\b/.test(p)) s.duration = 0.8;
  else if (/\b(very slow|slow(ly)?|gentle|gently|calm|lazy)\b/.test(p)) s.duration = 3.0;
  else if (s.subject === 'stickman') s.duration = s.motions.includes('run') ? 1.2 : 1.6;
  s.duration = Math.max(0.3, Math.min(s.duration, 10));
  if (contrast(s.color, s.background) < 3) s.background = lum(s.color) < 0.4 ? '#f4f2ee' : '#14151a';
  return s;
}

const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
export function lum(h) { const c = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const [r, g, b] = rgb(h); return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b); }
export function contrast(a, b) { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); }
const ease = u => 0.5 - 0.5 * Math.cos(Math.PI * u);
const R = Math.PI / 180, TAU = 2 * Math.PI;

export function pose(s, i, t) {
  const W = s.width, H = s.height, m = s.motions;
  const ph = (i / Math.max(1, s.count)) * (s.subject !== 'dots' ? 0.5 : 0.6);
  const tt = s.subject !== 'dots' ? (t + ph) % 1 : (((t - i * 0.15) % 1) + 1) % 1;
  const d = {dx: 0, dy: 0, rot: 0, sx: 1, sy: 1, op: 1, shadow: null};
  if (m.includes('bounce') || m.includes('jump')) {
    const h = H * (m.includes('bounce') ? 0.38 : 0.22), y = 4 * tt * (1 - tt);
    d.dy -= h * y;
    if (m.includes('bounce')) {
      if (y < 0.12) { const k = 1 - y / 0.12; d.sx = 1 + 0.28 * k; d.sy = 1 - 0.28 * k; }
      else { const st = Math.min(1, (0.6 - Math.min(y, 0.6)) / 0.5) * 0.12; d.sx = 1 - st; d.sy = 1 + st; }
    }
    d.shadow = 1 - 0.6 * y;
  }
  if (m.includes('spin')) d.rot += 360 * tt;
  if (m.includes('pulse')) {
    let k;
    if (s.subject === 'heart') k = 1 + 0.22 * (Math.exp(-(((tt - 0.12) / 0.05) ** 2)) + 0.7 * Math.exp(-(((tt - 0.32) / 0.05) ** 2)));
    else if (s.subject === 'dots') { const v = Math.max(0, Math.sin(TAU * tt)); k = 1 + 0.45 * v * v; d.dy -= H * 0.05 * v * v; d.op = 0.45 + 0.55 * v; }
    else k = 1 + 0.18 * Math.sin(TAU * tt);
    d.sx *= k; d.sy *= k;
  }
  if (m.includes('grow')) { const k = 0.55 + 0.45 * ease(1 - Math.abs(2 * tt - 1)); d.sx *= k; d.sy *= k; }
  if (m.includes('slide')) { d.dx += W * 0.3 / Math.max(1, Math.sqrt(s.count)) * Math.sin(TAU * tt); if (!m.includes('spin')) d.rot += 8 * Math.cos(TAU * tt); }
  if (m.includes('float')) { d.dy += H * 0.06 * Math.sin(TAU * tt); if (!m.includes('spin')) d.rot += 4 * Math.sin(TAU * tt + 1); }
  if (m.includes('orbit')) { const r = Math.min(W, H) * 0.28; d.dx += r * Math.cos(TAU * tt); d.dy += r * 0.6 * Math.sin(TAU * tt); }
  if (m.includes('shake')) { const env = Math.sin(Math.PI * tt); d.dx += 7 * env * Math.sin(TAU * 6 * tt); d.rot += 6 * env * Math.sin(TAU * 6 * tt + 0.5); }
  if (m.includes('fade')) d.op *= 0.15 + 0.85 * ease(1 - Math.abs(2 * tt - 1));
  if (s.subject === 'stickman') {
    const a = TAU * tt, run = m.includes('run'), sw = run ? 38 : 26, kn = run ? 50 : 30;
    Object.assign(d, {thL: sw * Math.sin(a), thR: -sw * Math.sin(a), shL: kn * Math.max(0, -Math.cos(a)), shR: kn * Math.max(0, Math.cos(a)),
      arL: -sw * 1.1 * Math.sin(a), arR: sw * 1.1 * Math.sin(a), foL: 25 + 15 * Math.sin(a), foR: 25 - 15 * Math.sin(a), lean: run ? 10 : 3});
    if (m.includes('walk') || run) { d.dx += (tt - 0.5) * W * (run ? 0.78 : 0.7); d.dy -= Math.abs(Math.sin(a)) * (run ? 9 : 5); }
    else { Object.assign(d, {thL: 9, thR: -9, shL: 0, shR: 0, lean: 0, arL: 18, foL: 10}); }
    if (m.includes('wave')) { d.arR = -150 + 12 * Math.sin(a); d.foR = -25 + 35 * Math.sin(2 * a); }
    if (m.includes('jump') || m.includes('bounce')) {
      const crouch = (tt < 0.1 || tt > 0.9) ? Math.max(0, 1 - 16 * tt * (1 - tt)) : 0;
      d.thL = d.thR = -30 * crouch - 10; d.shL = d.shR = 60 * crouch + 20;
    }
    if (m.includes('spin')) d.rot = 360 * tt;
  }
  return d;
}

export function layout(s, i) {
  const W = s.width, H = s.height, n = s.count;
  if (s.subject === 'dots') { const gap = Math.min(W / (n + 1), 46); return [W / 2 + (i - (n - 1) / 2) * gap, H / 2, gap * 0.32]; }
  let size = Math.min(W, H) * (n === 1 ? 0.16 : 0.5 / (n + 1));
  let cy = H * (s.motions.includes('bounce') || s.motions.includes('jump') ? 0.66 : 0.5);
  if (s.subject === 'stickman') { cy = H * 0.6; size = Math.min(W, H) * (n === 1 ? 0.28 : 0.2); }
  if (s.subject === 'text') size = Math.min(W, H) * 0.14;
  return [W * (i + 1) / (n + 1), cy, size];
}

export function shapePoints(subject, r) {
  const circ = k => Array.from({length: k}, (_, j) => [r * Math.cos(TAU * j / k), r * Math.sin(TAU * j / k)]);
  if (subject === 'ball' || subject === 'dots') return circ(48);
  if (subject === 'square') return [[-r, -r], [r, -r], [r, r], [-r, r]];
  if (subject === 'triangle') return [-90, 30, 150].map(a => [r * Math.cos(a * R), r * Math.sin(a * R)]);
  if (subject === 'diamond') return [[0, -r * 1.2], [r * 0.8, 0], [0, r * 1.2], [-r * 0.8, 0]];
  if (subject === 'star') return Array.from({length: 10}, (_, k) => { const rr = k % 2 ? r * 0.45 : r; return [rr * Math.cos((-90 + 36 * k) * R), rr * Math.sin((-90 + 36 * k) * R)]; });
  if (subject === 'heart') return Array.from({length: 60}, (_, k) => { const a = TAU * k / 60;
    return [16 * Math.sin(a) ** 3 * r / 16, -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a)) * r / 16]; });
  return [];
}

export function stick(d, r) {
  const lean = (d.lean || 0) * R, torso = r * 0.55, neck = [Math.sin(lean) * torso, -Math.cos(lean) * torso];
  const bones = [[[0, 0], neck]];
  const limb = (st, a1, a2, l1, l2) => { const b1 = a1 * R, b2 = (a1 + a2) * R;
    const j = [st[0] + Math.sin(b1) * l1, st[1] + Math.cos(b1) * l1], e = [j[0] + Math.sin(b2) * l2, j[1] + Math.cos(b2) * l2]; return [[st, j], [j, e]]; };
  bones.push(...limb([0, 0], d.thL || 0, -(d.shL || 0), r * 0.4, r * 0.4), ...limb([0, 0], d.thR || 0, -(d.shR || 0), r * 0.4, r * 0.4));
  const sh = [neck[0] * 0.85, neck[1] * 0.85];
  bones.push(...limb(sh, d.arL || 0, d.foL || 0, r * 0.3, r * 0.3), ...limb(sh, d.arR || 0, d.foR || 0, r * 0.3, r * 0.3));
  const hr = r * 0.13;
  return {bones, head: [neck[0] + Math.sin(lean) * hr * 1.1, neck[1] - hr * 1.1], hr};
}

const esc = t => String(t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

function svgShape(s, r) {
  const c = s.color;
  if (s.subject === 'ball' || s.subject === 'dots') return `<circle r="${r.toFixed(1)}" fill="${c}"/>`;
  if (s.subject === 'ring') return `<circle r="${r.toFixed(1)}" fill="none" stroke="${c}" stroke-width="${(r * 0.28).toFixed(1)}"/>`;
  if (s.subject === 'spinner') return Array.from({length: 12}, (_, j) => { const a = TAU * j / 12;
    return `<line x1="${(r * .55 * Math.cos(a)).toFixed(1)}" y1="${(r * .55 * Math.sin(a)).toFixed(1)}" x2="${(r * Math.cos(a)).toFixed(1)}" y2="${(r * Math.sin(a)).toFixed(1)}" stroke="${c}" stroke-width="${(r * .16).toFixed(1)}" stroke-linecap="round" opacity="${(0.15 + 0.85 * j / 11).toFixed(2)}"/>`; }).join('');
  if (s.subject === 'text') return `<text text-anchor="middle" dominant-baseline="central" font-family="system-ui,sans-serif" font-weight="800" font-size="${r.toFixed(1)}" fill="${c}">${esc(s.text)}</text>`;
  return `<polygon points="${shapePoints(s.subject, r).map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}" fill="${c}"/>`;
}

// Inline SVG with its own CSS keyframes (GPU-composited transforms: cheap on phones).
export function svg(s, uid = 'x' + Math.random().toString(36).slice(2, 7), steps = 40) {
  const css = [], body = [], dur = `${s.duration.toFixed(2)}s`;
  for (let i = 0; i < s.count; i++) {
    const [cx, cy, r] = layout(s, i);
    const ks = Array.from({length: steps + 1}, (_, k) => pose(s, i, k / steps));
    css.push(`@keyframes ${uid}a${i}{${ks.map((d, k) => `${(100 * k / steps).toFixed(1)}%{transform:translate(${d.dx.toFixed(1)}px,${d.dy.toFixed(1)}px) rotate(${d.rot.toFixed(1)}deg) scale(${d.sx.toFixed(3)},${d.sy.toFixed(3)});opacity:${d.op.toFixed(3)}}`).join('')}}.${uid}a${i}{animation:${uid}a${i} ${dur} linear infinite;transform-origin:0 0}`);
    if (ks[0].shadow !== null) {
      css.push(`@keyframes ${uid}s${i}{${ks.map((d, k) => `${(100 * k / steps).toFixed(1)}%{transform:translate(${d.dx.toFixed(1)}px,0) scale(${(0.9 * d.shadow + 0.2).toFixed(3)},1);opacity:${(0.25 + 0.35 * d.shadow).toFixed(3)}}`).join('')}}.${uid}s${i}{animation:${uid}s${i} ${dur} linear infinite;transform-origin:0 0}`);
      body.push(`<g transform="translate(${cx.toFixed(1)},${(cy + r * (s.subject !== 'stickman' ? 1.05 : 0.82)).toFixed(1)})"><ellipse class="${uid}s${i}" rx="${r.toFixed(1)}" ry="${(r * 0.18).toFixed(1)}" fill="#000"/></g>`);
    }
    let shape;
    if (s.subject === 'stickman') {
      const fr = ks.map(d => stick(d, r)), w = Math.max(2, r * 0.06).toFixed(1);
      shape = fr[0].bones.map((_, b) => `<polyline fill="none" stroke="${s.color}" stroke-width="${w}" stroke-linecap="round"><animate attributeName="points" dur="${dur}" repeatCount="indefinite" values="${fr.map(f => f.bones[b].map(p => p.map(v => v.toFixed(1)).join(',')).join(' ')).join(';')}"/></polyline>`).join('') +
        `<circle r="${(r * 0.13).toFixed(1)}" fill="none" stroke="${s.color}" stroke-width="${w}"><animate attributeName="cx" dur="${dur}" repeatCount="indefinite" values="${fr.map(f => f.head[0].toFixed(1)).join(';')}"/><animate attributeName="cy" dur="${dur}" repeatCount="indefinite" values="${fr.map(f => f.head[1].toFixed(1)).join(';')}"/></circle>`;
    } else shape = svgShape(s, r);
    body.push(`<g transform="translate(${cx.toFixed(1)},${cy.toFixed(1)})"><g class="${uid}a${i}">${shape}</g></g>`);
  }
  return `<svg viewBox="0 0 ${s.width} ${s.height}" role="img" aria-label="${esc(s.title)}" style="background:${s.background};width:100%;height:auto;display:block;border-radius:12px"><style>${css.join('')}@media (prefers-reduced-motion: reduce){svg *{animation-play-state:paused}}</style>${body.join('')}</svg>`;
}

// Canvas frames for GIF export and the self-check.
export function drawFrame(ctx, s, t) {
  const {width: W, height: H} = s;
  ctx.fillStyle = s.background; ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < s.count; i++) {
    const [cx, cy, r] = layout(s, i), d = pose(s, i, t);
    if (d.shadow !== null && s.subject !== 'text') {
      const gy = cy + r * (s.subject !== 'stickman' ? 1.05 : 0.82), w = r * (0.9 * d.shadow + 0.2);
      ctx.save(); ctx.globalAlpha = 0.25 + 0.35 * d.shadow; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.ellipse(cx + d.dx, gy, w, w * 0.18, 0, 0, TAU); ctx.fill(); ctx.restore();
    }
    ctx.save(); ctx.translate(cx + d.dx, cy + d.dy); ctx.rotate(d.rot * R); ctx.scale(d.sx, d.sy); ctx.globalAlpha = d.op;
    ctx.fillStyle = ctx.strokeStyle = s.color; ctx.lineCap = 'round';
    if (s.subject === 'stickman') {
      const k = stick(d, r); ctx.lineWidth = Math.max(2, r * 0.06);
      for (const [a, b] of k.bones) { ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke(); }
      ctx.beginPath(); ctx.arc(k.head[0], k.head[1], k.hr, 0, TAU); ctx.stroke();
    } else if (s.subject === 'ring') { ctx.lineWidth = r * 0.28; ctx.beginPath(); ctx.arc(0, 0, r, 0, TAU); ctx.stroke(); }
    else if (s.subject === 'spinner') {
      ctx.lineWidth = r * 0.16;
      for (let j = 0; j < 12; j++) { const a = TAU * j / 12; ctx.globalAlpha = d.op * (0.15 + 0.85 * j / 11); ctx.beginPath();
        ctx.moveTo(r * .55 * Math.cos(a), r * .55 * Math.sin(a)); ctx.lineTo(r * Math.cos(a), r * Math.sin(a)); ctx.stroke(); }
    } else if (s.subject === 'text') { ctx.font = `800 ${r}px system-ui,sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(s.text, 0, 0); }
    else { const pts = shapePoints(s.subject, r); ctx.beginPath(); pts.forEach(([x, y], j) => j ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fill(); }
    ctx.restore();
  }
}

export function frameCount(s, fps = 20) { return Math.max(8, Math.min(72, Math.round(s.duration * fps))); }

// Self-check: it moves, and nothing touches the top/bottom edge.
export function check(s) {
  const c = new OffscreenCanvas(s.width / 2, s.height / 2), ctx = c.getContext('2d', {willReadFrequently: true});
  ctx.scale(0.5, 0.5);
  const n = frameCount(s), imgs = [];
  for (let k = 0; k < n; k++) { drawFrame(ctx, s, k / n); imgs.push(ctx.getImageData(0, 0, c.width, c.height).data); }
  let maxDiff = 0, edge = false;
  const bg = rgb(s.background);
  for (let k = 0; k < n; k++) {
    const a = imgs[k], b = imgs[(k + 1) % n]; let diff = 0;
    for (let j = 0; j < a.length; j += 16) diff += Math.abs(a[j] - b[j]);
    maxDiff = Math.max(maxDiff, diff / (a.length / 16));
    for (const row of [0, c.height - 1]) for (let x = 0; x < c.width; x += 2) { const o = (row * c.width + x) * 4;
      if (Math.abs(a[o] - bg[0]) + Math.abs(a[o + 1] - bg[1]) + Math.abs(a[o + 2] - bg[2]) > 180) edge = true; }
  }
  return {frames: n, moves: maxDiff > 0.05, touchesEdge: edge};
}

// GIF export (gifenc); returns a Uint8Array.
export async function gif(s, scale = 1) {
  const {GIFEncoder, quantize, applyPalette} = await import('./vendor/gifenc.esm.js');
  const W = Math.round(s.width * scale), H = Math.round(s.height * scale);
  const c = new OffscreenCanvas(W, H), ctx = c.getContext('2d', {willReadFrequently: true});
  ctx.scale(scale, scale);
  const n = frameCount(s), delay = Math.round(1000 * s.duration / n), enc = GIFEncoder();
  for (let k = 0; k < n; k++) {
    drawFrame(ctx, s, k / n);
    const data = ctx.getImageData(0, 0, W, H).data, pal = quantize(data, 64), idx = applyPalette(data, pal);
    enc.writeFrame(idx, W, H, {palette: pal, delay, repeat: 0});
    if (k % 6 === 5) await new Promise(r => setTimeout(r));  // stay responsive
  }
  enc.finish();
  return enc.bytes();
}
