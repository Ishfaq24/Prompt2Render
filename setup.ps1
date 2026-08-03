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

Say "installing fdx deps + Manim (Manim is only used by the 'fdx manim' hand-authored escape hatch)"
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
& .\.venv\Scripts\python.exe -m pip install "manim==0.19.0" --quiet

# ------------------------------------------------------------------- .env
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Say "created .env — put your GEMINI_API_KEY in it (used by 'fdx scenes')"
}

# ---------------------------------------------------------- local models
Say "fetching the local ASR/VAD/voice models (one time, a few hundred MB)"
& .\.venv\Scripts\python.exe fdx.py models --asr base.en --vad --kokoro

# ----------------------------------------------------------------- verify
Say "verifying"
& .\.venv\Scripts\python.exe fdx.py doctor

Write-Host @"

Setup done. Every new PowerShell session, activate first:

  .\.venv\Scripts\Activate.ps1
  python fdx.py new my-first-video
  # write projects/my-first-video/script.md, then:
  python fdx.py build my-first-video

`build` runs voice -> align -> scenes -> stills -> plan -> encode -> finish ->
check. Put your Gemini key in .env first -- 'fdx scenes' needs it.

Or skip the terminal for the long stages:

  python fdx.py serve

"@ -ForegroundColor Green
