#!/usr/bin/env bash
# fdx setup — detects your OS and installs everything the pipeline needs.
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

say "installing fdx python deps"
pip install -r requirements.txt

say "installing Manim Community"
pip install "manim==0.19.0"

# ------------------------------------------------------------- Code2Video
C2V_DIR="${CODE2VIDEO_DIR:-$(cd .. && pwd)/Code2Video}"
if [ ! -d "$C2V_DIR" ]; then
  say "cloning Code2Video into $C2V_DIR"
  git clone --depth 1 https://github.com/showlab/Code2Video.git "$C2V_DIR"
else
  say "Code2Video already at $C2V_DIR"
fi

say "installing Code2Video deps"
( cd "$C2V_DIR/src" && pip install -r requirements.txt ) \
  || warn "Code2Video deps failed — you can still use 'fdx import' and 'fdx placeholders'"

# ------------------------------------------------------------------- .env
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i.bak "s|^CODE2VIDEO_DIR=.*|CODE2VIDEO_DIR=$C2V_DIR|" .env && rm -f .env.bak
  say "created .env — put your API keys in it"
fi

# ----------------------------------------------------------------- verify
say "verifying"
python3 - <<'PY'
import shutil, sys
ok = True
for tool in ("ffmpeg", "ffprobe", "manim"):
    found = shutil.which(tool)
    print(f"  {tool:10s} {'OK  ' + found if found else 'MISSING'}")
    ok &= bool(found)
try:
    import edge_tts  # noqa: F401
    print("  edge-tts   OK")
except ImportError:
    print("  edge-tts   MISSING (fine if you record your own voice)")
sys.exit(0 if ok else 1)
PY

cat <<'EOF'

Setup done.

  source .venv/bin/activate
  python fdx.py new my-first-video
  # write projects/my-first-video/script.md
  python fdx.py run my-first-video --tts

Also fill in Code2Video's own src/api_config.json — it reads keys from
there, not from .env.
EOF
