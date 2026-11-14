// Runs Python on the phone (Pyodide, bundled) in its own thread with a time limit enforced by the app.
import {loadPyodide} from './vendor/pyodide/pyodide.mjs';

let py = null;
self.onmessage = async ({data}) => {
  const {id, code} = data;
  try {
    if (!py) py = await loadPyodide({indexURL: new URL('./vendor/pyodide/', import.meta.url).href});
    let out = '';
    py.setStdout({batched: s => { out += s + '\n'; }});
    py.setStderr({batched: s => { out += s + '\n'; }});
    try {
      await py.runPythonAsync(code);
      postMessage({id, ok: true, output: out});
    } catch (e) {
      const msg = String(e.message || e).split('\n').filter(l => !l.includes('/lib/python') && !l.includes('_pyodide')).join('\n');
      postMessage({id, ok: false, output: out + msg});
    }
  } catch (e) {
    postMessage({id, ok: false, output: 'Python failed to start: ' + e});
  }
};
