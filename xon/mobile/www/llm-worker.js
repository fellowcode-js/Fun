// Runs the local model off the UI thread so the app never freezes.
// Speed choices: WebGPU (phone GPU) when available, else multi-threaded WASM SIMD on the CPU with an 8-bit model.
// The model downloads once from Hugging Face (free, no key) and is cached on the phone.
import {AutoTokenizer, AutoModelForCausalLM, TextStreamer, InterruptableStoppingCriteria, env} from './vendor/transformers.min.js';

env.allowLocalModels = false;
env.useBrowserCache = true;
env.backends.onnx.wasm.wasmPaths = new URL('./vendor/', import.meta.url).href;  // bundled runtime, nothing from a CDN

const MODEL = 'onnx-community/Qwen2.5-Coder-0.5B-Instruct';
let tok = null, model = null, device = null, loading = null;
const stopper = new InterruptableStoppingCriteria();

async function pickDevice(pref) {
  if (pref !== 'cpu' && self.navigator?.gpu) {
    try { const a = await navigator.gpu.requestAdapter({powerPreference: 'high-performance'}); if (a) return 'webgpu'; } catch (e) {}
  }
  return 'wasm';
}

async function load(opts) {
  if (model && (!opts.device || opts.device === 'auto' || (opts.device === 'gpu') === (device === 'webgpu'))) return;
  device = await pickDevice(opts.device === 'cpu' ? 'cpu' : 'auto');
  const threads = self.crossOriginIsolated ? Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 4) - 1)) : 1;
  env.backends.onnx.wasm.numThreads = threads;
  const progress = p => { if (p.status === 'progress') postMessage({type: 'progress', file: p.file, loaded: p.loaded, total: p.total}); };
  postMessage({type: 'status', text: `loading model on ${device === 'webgpu' ? 'GPU' : `CPU (${threads} thread${threads > 1 ? 's' : ''})`}`});
  tok = await AutoTokenizer.from_pretrained(MODEL, {progress_callback: progress});
  try {
    model = await AutoModelForCausalLM.from_pretrained(MODEL, {device, dtype: device === 'webgpu' ? 'q4f16' : 'q8', progress_callback: progress});
  } catch (e) {  // some phone GPUs lack fp16 shaders: fall back to the CPU path
    if (device !== 'webgpu') throw e;
    device = 'wasm';
    model = await AutoModelForCausalLM.from_pretrained(MODEL, {device, dtype: 'q8', progress_callback: progress});
  }
  // warm-up: compiles kernels so the first real answer starts fast
  const w = tok.apply_chat_template([{role: 'user', content: 'hi'}], {add_generation_prompt: true, return_dict: true});
  await model.generate({...w, max_new_tokens: 1});
  postMessage({type: 'ready', device, threads, isolated: self.crossOriginIsolated});
}

async function generate({id, messages, max_new_tokens = 320, temperature = 0.2}) {
  const inputs = tok.apply_chat_template(messages, {add_generation_prompt: true, return_dict: true});
  let n = 0, t0 = 0;
  const streamer = new TextStreamer(tok, {skip_prompt: true, skip_special_tokens: true, callback_function: text => {
    if (!t0) t0 = performance.now();
    n++; postMessage({type: 'token', id, text});
  }});
  stopper.reset();
  const tStart = performance.now();
  await model.generate({...inputs, max_new_tokens, do_sample: temperature > 0, temperature: temperature || undefined, top_p: 0.9,
    repetition_penalty: 1.05, streamer, stopping_criteria: stopper});
  const secs = (performance.now() - (t0 || tStart)) / 1000;
  postMessage({type: 'done', id, tokens: n, seconds: +((performance.now() - tStart) / 1000).toFixed(1),
               tps: n > 1 ? +((n - 1) / secs).toFixed(1) : 0, first_token_ms: t0 ? Math.round(t0 - tStart) : null, device});
}

self.onmessage = async ({data}) => {
  try {
    if (data.type === 'load') { loading = loading || load(data); await loading; loading = null; }
    else if (data.type === 'generate') { if (!model) { loading = loading || load(data); await loading; loading = null; } await generate(data); }
    else if (data.type === 'stop') stopper.interrupt();
    else if (data.type === 'unload') { await model?.dispose?.(); model = null; tok = null; postMessage({type: 'unloaded'}); }
  } catch (e) {
    loading = null;
    postMessage({type: 'error', id: data.id, error: String(e?.message || e)});
  }
};
