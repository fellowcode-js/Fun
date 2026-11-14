# XON one-command install for Windows (PowerShell). UNTESTED on real Windows: XON was built and tested on Linux.
#   Run from the xon folder:   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   Skip the ~1 GB model:      $env:XON_SKIP_MODEL = "1"; powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
function Say($m) { Write-Host "`n==> $m" -ForegroundColor Yellow }

$py = $null
foreach ($cand in @("py -3.12", "py -3.11", "py -3.10", "python")) {
  try {
    $exe, $arg = $cand.Split(" ", 2)
    $ok = & $exe $arg -c "import sys; print(sys.version_info >= (3,10))" 2>$null
    if ($ok -eq "True") { $py = $cand; break }
  } catch {}
}
if (-not $py) {
  Write-Host "XON needs Python 3.10+. Install it from https://python.org (tick 'Add python.exe to PATH') and re-run."
  exit 1
}
$exe, $arg = $py.Split(" ", 2)
Say "creating virtual environment .venv (using $py)"
if (-not (Test-Path .venv)) { & $exe $arg -m venv .venv }
$vpy = Join-Path (Resolve-Path .venv) "Scripts\python.exe"
& $vpy -m pip install -q --upgrade pip

Say "installing PyTorch"
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  & $vpy -m pip install -q torch --index-url https://download.pytorch.org/whl/cu124
} else {
  & $vpy -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
}
Say "installing XON and its dependencies"
& $vpy -m pip install -q -r scripts\requirements.txt
& $vpy -m pip install -q -e .
Say "installing headless Chromium (design tools, screenshots)"
& $vpy -m playwright install chromium
& $vpy scripts\build_evalsets.py | Out-Null

if ($env:XON_SKIP_MODEL -ne "1") {
  Say "downloading the local coder model (Qwen2.5-Coder-0.5B-Instruct, Apache-2.0, ~1 GB)"
  & $vpy -c "from xon import config; from xon.lm.pretrained import DEFAULT, PretrainedCoder; cfg = config.load(); c = PretrainedCoder(cfg['lm'].get('pretrained', DEFAULT), cache_dir=config.path(cfg, 'checkpoints') / 'pretrained'); print('model OK')"
}
$here = (Get-Location).Path
Write-Host @"

XON installed.
  .venv\Scripts\Activate.ps1
  xon doctor
  xon studio --open                 # the app (local model, no API key needed)
  claude mcp add xon -- "$here\.venv\Scripts\xon.exe" mcp --root "$here"
                                    # let Claude Code use XON (free with your Claude login)
"@
