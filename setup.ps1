# fdx setup for native Windows (no WSL).
# Run in PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup.ps1
# Safe to re-run.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($m)  { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }

# ------------------------------------------------------------- prerequisites
Say "checking winget"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Warn "winget missing. Install 'App Installer' from the Microsoft Store, then re-run."
  exit 1
}

Say "installing Python, Git, ffmpeg, MiKTeX"
# --silent so none of these open an installer wizard mid-script.
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements 2>$null
winget install -e --id Git.Git           --silent --accept-package-agreements --accept-source-agreements 2>$null
winget install -e --id Gyan.FFmpeg       --silent --accept-package-agreements --accept-source-agreements 2>$null
winget install -e --id MiKTeX.MiKTeX     --silent --accept-package-agreements --accept-source-agreements 2>$null

Say "refreshing PATH for this session"
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

foreach ($t in @("python","git","ffmpeg","ffprobe")) {
  if (Get-Command $t -ErrorAction SilentlyContinue) { Write-Host "  $t OK" }
  else { Warn "$t not on PATH yet — close PowerShell, reopen, and re-run this script" }
}

# ------------------------------------------------------------------- python
Say "creating virtualenv .venv"
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel --quiet

Say "installing fdx deps + Manim"
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
& .\.venv\Scripts\python.exe -m pip install "manim==0.19.0" --quiet

# --------------------------------------------------------------- Code2Video
$c2v = Join-Path (Split-Path $PSScriptRoot -Parent) "Code2Video"
if (-not (Test-Path $c2v)) {
  Say "cloning Code2Video into $c2v"
  git clone --depth 1 https://github.com/showlab/Code2Video.git $c2v
} else { Say "Code2Video already at $c2v" }

Say "installing Code2Video deps"
try { & .\.venv\Scripts\python.exe -m pip install -r (Join-Path $c2v "src\requirements.txt") --quiet }
catch { Warn "Code2Video deps failed — 'fdx import' and 'fdx placeholders' still work" }

# ------------------------------------------------------------------- .env
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  (Get-Content .env) -replace '^CODE2VIDEO_DIR=.*', "CODE2VIDEO_DIR=$($c2v -replace '\\','/')" |
    Set-Content .env
  Say "created .env — put your Gemini key in it"
}

# ----------------------------------------------------------------- verify
Say "verifying"
& .\.venv\Scripts\python.exe -c @"
import shutil
for t in ('ffmpeg','ffprobe','bash'):
    p = shutil.which(t)
    print(f'  {t:9s} ' + ('OK  ' + p if p else 'MISSING'))
try:
    import manim; print('  manim     OK ' + manim.__version__)
except Exception as e: print('  manim     MISSING', e)
try:
    import edge_tts; print('  edge-tts  OK')
except ImportError: print('  edge-tts  MISSING')
"@

Write-Host @"

Setup done. Every new PowerShell session, activate first:

  .\.venv\Scripts\Activate.ps1
  python fdx.py new smoke-test
  python fdx.py placeholders smoke-test
  python fdx.py assemble smoke-test --tts

Then put your Gemini key in Code2Video\src\api_config.json as well as .env.

"@ -ForegroundColor Green
