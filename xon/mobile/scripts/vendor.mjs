// Copies the on-device runtimes into www/vendor (run after `npm ci`). Nothing is fetched from a CDN at runtime.
import {cpSync, mkdirSync, rmSync} from 'node:fs';
const nm = new URL('../node_modules/', import.meta.url), out = new URL('../www/vendor/', import.meta.url);
rmSync(out, {recursive: true, force: true});
mkdirSync(new URL('pyodide/', out), {recursive: true});
const cp = (from, to) => cpSync(new URL(from, nm), new URL(to, out));
cp('@huggingface/transformers/dist/transformers.min.js', 'transformers.min.js');
for (const f of ['ort-wasm-simd-threaded.asyncify.mjs', 'ort-wasm-simd-threaded.asyncify.wasm', 'ort-wasm-simd-threaded.jsep.mjs', 'ort-wasm-simd-threaded.jsep.wasm'])
  cp(`onnxruntime-web/dist/${f}`, f);
cp('gifenc/dist/gifenc.esm.js', 'gifenc.esm.js');
for (const f of ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json'])
  cp(`pyodide/${f}`, `pyodide/${f}`);
console.log('vendor files copied to www/vendor');
