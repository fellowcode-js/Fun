# XON Studio on your phone

A standalone Android app. Everything runs on the phone: no computer, no API keys, nothing sent anywhere. The only
network use is downloading the coder model once (Wi-Fi recommended).

## Get it
1. On your phone, open the repository's **Releases** page and download **XON-Studio.apk** (release
   "XON Studio for Android"). It is rebuilt automatically by GitHub every time the app changes
   (`.github/workflows/xon-studio-apk.yml`); you can also start a build from the Actions tab.
2. Open the file, allow "Install unknown apps" for your browser when Android asks, tap **Install**.
3. Open XON Studio, send a first chat message. The model downloads once (about 560 MB on GPU phones, 640 MB on CPU
   phones) and stays cached. New versions of the app install over the old one and keep the model.

## What's in it
| Tab | What it does |
|---|---|
| Chat | Coding chat with Qwen2.5-Coder-0.5B running on the phone. Python code blocks get a **Run** button (real Python on the phone via Pyodide). |
| Helpers | Make sub-agents: an **animator** (description -> animation, **Save GIF** puts it in Downloads), a **coder** (writes code + tests, runs them, retries once if they fail), and game characters (**Greta** the shopkeeper, **Volk** the guard) in a demo town. Each helper only gets its own tools. |
| Helpers: any task | Ask for a sub-agent for anything ("a sub-agent for 3D modeling", "a helper that writes song lyrics"), in Helpers or straight from Chat. XON makes a specialist for that task with its own sandbox: it writes files there (FILE: name + code block), runs Python it wrote inside the sandbox, fixes it once if it fails, and you tap a file to save it to Downloads. |
| Speed | Brain (On this phone / API), Cool mode, Fast / Balanced / Best, engine choice, memory saver, a speed test and what your phone supports. |

Needs the desktop version: training the XON LM, Exhort, C++ (phones have no compiler), design critique.

## Ollama key (one step)
Speed tab > **Ollama key** > paste your key from ollama.com (Settings > Keys) > **Use key** (pasting is enough).
XON checks the key with Ollama, picks the best cloud model the key can use (gpt-oss:120b first), and switches chat
and sub-agents to it. Nothing else to set up. A wrong key is refused with a message. The key stays on the phone.

## Sub-agents and XON's model
Sub-agents think with **XON's model** (on the phone) by default, through XON's loop: write the files, add its own
asserts to code, run in its own sandbox, fix from the error (3 tries, more sampling each try). "Sub-agents think
with: API" runs the same loop on Ollama/your server. Coding helpers use this loop too now.

## API brain (optional, off by default)
Speed tab > Brain > **API**. Pick **Ollama** (address like `http://192.168.1.10:11434`, model like `llama3.2`) or any
**OpenAI-compatible** server (LM Studio, llama.cpp server, etc., address ending in `/v1`, optional key). Tap **Test
connection**. The phone then does no model work at all: fastest, coolest. On the PC start Ollama with
`OLLAMA_HOST=0.0.0.0 ollama serve` so the phone can reach it on Wi-Fi. Requests are made natively by the app, so plain
`http://` on your home network works. The key stays on the phone.

## Heat (Cool mode, on by default)
- Uses 2 CPU cores instead of every core, and the GPU in low-power mode: far less heat for a small speed cost.
- Short bursts (answers capped at 320 tokens, 160 when warm) with a short rest between answers.
- Watches tokens/s: a phone that heats up throttles itself, so a drop below 60% of its best speed means "hot"; XON
  then rests 4 s between answers and shortens them until speed recovers.
- Stops generating when you leave the app and frees the model after 1 minute in the background (3 minutes idle in the app).

## How it stays fast
- **The model never runs on the screen's thread.** It runs in a background worker, so scrolling and typing stay smooth
  while it thinks; Python runs in a second worker with a 20 s limit.
- **GPU when the phone has one.** With WebGPU (recent Android, Chrome/WebView 121+) the model runs on the GPU with a
  4-bit model. Otherwise it uses the CPU with an 8-bit model and **several cores**: the app serves itself with
  cross-origin isolation, which unlocks multi-threaded WebAssembly (SIMD). It leaves one core free for the UI.
- **Kernels are warmed up** right after loading, so the first real answer starts quickly.
- **Short context.** Fast keeps the last 2 exchanges and up to 192 new tokens, Balanced 4 and 360, Best 8 and 700.
  Less context = faster answers and less memory.
- **Memory saver.** After 10 minutes idle the model is unloaded (setting on by default); it reloads from the phone's
  cache in seconds. "Free memory now" does it immediately.
- **Everything bundled.** The runtimes (ONNX Runtime, Pyodide, GIF encoder) ship inside the APK, stored uncompressed
  so they load fast. Animations play as SVG/CSS transforms, which the GPU composites for almost no battery.
- **Speed test** reports tokens/second and suggests a mode.

Tips: close heavy apps before long answers; a hot phone slows itself down (thermal throttling), so give it a break
on long sessions; Fast mode on older phones.

## Build it yourself
```bash
cd xon/mobile && npm ci --ignore-scripts && node scripts/vendor.mjs   # bundle the runtimes into www/vendor
python3 scripts/serve.py 8088 www                                      # try it in a desktop browser
cd android && ./gradlew assembleDebug                                  # APK (needs the Android SDK)
```
The APK is signed with a fixed debug key (`android/app/xon-debug.keystore`, not secret) so updates install over
each other. It is meant for sideloading, not the Play Store.

Related: [studio.md](studio.md) (the desktop app), [subagents.md](subagents.md).
