#!/usr/bin/env bash
# prompt2render setup — detects your OS and installs everything the pipeline needs.
# Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- detect OS
OS="unknown"
case "$(uname -s)" in
  Linux*)  OS="linux"; grep -qi microsoft /proc/version 2>/dev/null && OS="wsl" ;;
  Darwin*) OS="macos" ;;
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac
say "detected: $OS"

if [ "$OS" = "windows" ]; then
  warn "Native Windows is the painful path for Manim + LaTeX."
  warn "Install WSL2 (wsl --install -d Ubuntu), then re-run this inside it."
  exit 1
fi

# ------------------------------------------------------------ system deps
say "installing system dependencies (needs sudo)"
if [ "$OS" = "macos" ]; then
  command -v brew >/dev/null || {
    warn "Homebrew required: https://brew.sh"; exit 1; }
  brew install python@3.12 ffmpeg cairo pango pkg-config || true
  brew install --cask mactex-no-gui || warn "MacTeX skipped — MathTex will fail without it"
else
  sudo apt-get update
  sudo apt-get install -y \
    python3 python3-pip python3-venv git ffmpeg \
    build-essential pkg-config libcairo2-dev libpango1.0-dev \
    texlive texlive-latex-extra texlive-fonts-extra texlive-science \
    fonts-dejavu dvisvgm
fi

# ----------------------------------------------------------------- python
say "creating virtualenv .venv"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip wheel

say "installing prompt2render python deps"
pip install -r requirements.txt

# Manim version is pinned in requirements.txt and mirrored by
# prompt2render/manimver.py. P2R_MANIM_VERSION installs a different one
# (0.19.0 reproduces the Code2Video comparison - docs/MANIM_EXPERIMENT_PROTOCOL.md).
MANIM_VERSION="${P2R_MANIM_VERSION:-0.21.0}"

say "installing Manim Community ${MANIM_VERSION} (drives the --manim scene backend and the 'prompt2render manim' escape hatch)"
pip install "manim==${MANIM_VERSION}"

# ------------------------------------------------------------------- .env
if [ ! -f .env ]; then
  cp .env.example .env
  say "created .env — put your GEMINI_API_KEY in it (used by 'prompt2render scenes')"
fi

# ---------------------------------------------------------- local models
say "fetching the local ASR/VAD/voice models (one time, a few hundred MB)"
python prompt2render.py models --asr base.en --vad --kokoro

# ----------------------------------------------------------------- verify
say "verifying"
python prompt2render.py doctor

cat <<'EOF'

Setup done.

  source .venv/bin/activate
  python prompt2render.py new my-first-video
  # write projects/my-first-video/script.md, then:
  python prompt2render.py build my-first-video

`build` runs voice -> align -> scenes -> stills -> plan -> encode -> finish ->
check. Put your Gemini key in .env first — 'prompt2render scenes' needs it.

Or skip the terminal for the long stages:

  python prompt2render.py serve
EOF
