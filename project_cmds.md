# 📖 Prompt2Render — Complete CLI & Command Reference Guide

This document is the single, exhaustive command reference for **Prompt2Render**. It details every CLI command, subcommand, option, flag, standalone utility script, testing suite, installer, and environment variable in the repository.

---

## 📑 Table of Contents

1. [⚡ Quick-Start Cheat Sheet](#1--quick-start-cheat-sheet)
2. [🏗️ Master CLI: Project Scaffolding & Environment](#2-️-master-cli-project-scaffolding--environment)
3. [🚀 Master CLI: End-to-End Pipeline Execution](#3--master-cli-end-to-end-pipeline-execution)
4. [🧩 Master CLI: Modular Pipeline Stages](#4--master-cli-modular-pipeline-stages)
5. [🌐 Master CLI: Multilingual Video Generation](#5--master-cli-multilingual-video-generation)
6. [🛡️ Master CLI: Self-Correction & Harness Operations](#6-️-master-cli-self-correction--harness-operations)
7. [🧰 Master CLI: Escape Hatches & Manual Overrides](#7--master-cli-escape-hatches--manual-overrides)
8. [🔬 Standalone Diagnostic & Utility Scripts (`tools/`)](#8--standalone-diagnostic--utility-scripts-tools)
9. [🧪 Test Suite Execution (`pytest`)](#9--test-suite-execution-pytest)
10. [🐳 Setup, Environment & Docker Commands](#10--setup-environment--docker-commands)
11. [⚙️ Environment Variables & Performance Tuning](#11-️-environment-variables--performance-tuning)
12. [📋 Practical Workflows & Examples](#12--practical-workflows--examples)

---

## 1. ⚡ Quick-Start Cheat Sheet

| Goal | Command |
| :--- | :--- |
| **Verify Environment & Dependencies** | `python prompt2render.py doctor --render-test` |
| **Download Required Models** | `python prompt2render.py models --asr base.en --vad --kokoro` |
| **Create New Video Project** | `python prompt2render.py new binary-search --title "Binary Search Explained" --ai` |
| **One-Shot Automated Generation** | `python prompt2render.py auto binary-search --harness --strict --manim` |
| **Standard Step-by-Step Build** | `python prompt2render.py build binary-search` |
| **Start Web Studio Dashboard** | `python prompt2render.py serve --port 8787` |
| **Repair Scene 03 with Manim** | `python prompt2render.py repair binary-search --section 3 --manim` |
| **Deterministic Scene Verification** | `python prompt2render.py verify binary-search --section 3` |
| **Multilingual Video (Hindi)** | `python prompt2render.py multilingual "K-Means Clustering" --lang hi` |
| **Run Full Pytest Test Suite** | `pytest` |

---

## 2. 🏗️ Master CLI: Project Scaffolding & Environment

All core commands can be executed via either:
- `python prompt2render.py <command>`
- `python -m prompt2render <command>`

### `new` — Scaffold a New Project
Creates a directory under `projects/<slug>/` containing `script.md` with structured metadata headers.

```bash
python prompt2render.py new <slug> [OPTIONS]
```

**Options:**
- `<slug>` *(Required)*: Unique project directory slug (e.g. `binary-search`, `bubble-sort`).
- `--title "<string>"`: Human-readable video title. Defaults to title-cased slug.
- `--minutes <float>`: Target length in minutes. Scales section count (default: 10 min = 6 sections).
- `--sections <int>`: Explicitly set section count instead of calculating from `--minutes`.
- `--ai`: Prompts Gemini to generate custom section titles and visual briefs (`> ANIM:`) for this topic instead of using generic boilerplate.
- `--aspect {16:9, 9:16, 1:1, portrait, landscape, shorts, square}`: Aspect ratio profile (default: `16:9`).

**Example:**
```bash
python prompt2render.py new neural-networks --title "How Neural Networks Learn" --minutes 3.5 --ai --aspect 16:9
```

---

### `doctor` — Environment & Toolchain Diagnostics
Audits Python version, virtualenv, FFmpeg, FFprobe, LaTeX (`dvisvgm`, `xelatex`), Manim CE, GPU encoder (`h264_nvenc`), and local model caches.

```bash
python prompt2render.py doctor [OPTIONS]
```

**Options:**
- `--render-test`: Renders an actual 1080p Manim test scene and validates dimensions (1920x1080 @ 30fps) with `ffprobe`.

**Example:**
```bash
python prompt2render.py doctor --render-test
```

---

### `models` — Fetch & Cache Local Model Weights
Downloads neural speech synthesis (Kokoro-82M) and forced alignment (Whisper, Silero VAD) weights.

```bash
python prompt2render.py models [OPTIONS]
```

**Options:**
- `--asr {tiny.en, base.en, small.en}`: Whisper ASR model variant (default: `base.en`).
- `--vad`: Silero Voice Activity Detection model weights.
- `--kokoro`: Kokoro-82M neural TTS model weights (~350 MB).
- `--kokoro-int8`: Quantized INT8 Kokoro model weights (~92 MB).
- `--force`: Re-download even if files already exist locally.

**Example:**
```bash
python prompt2render.py models --asr base.en --vad --kokoro
```

---

### `voices` — List Available Neural TTS Voices
Prints all supported voices available in the local Kokoro voice registry.

```bash
python prompt2render.py voices
```

---

### `languages` — List Multilingual Languages & Scripts
Displays all registered languages, writing systems (Devanagari, Perso-Arabic, Latin), text direction (LTR/RTL), and system fonts.

```bash
python prompt2render.py languages
```

---

### `serve` — Launch Interactive Web Studio Dashboard
Starts the FastAPI + SSE interactive web dashboard with visual canvas preview, timeline editor, and pipeline triggers.

```bash
python prompt2render.py serve [OPTIONS]
```

**Options:**
- `--host <ip>`: Bind address (default: `127.0.0.1`).
- `--port <int>`: Port number (default: `8787`).
- `--reload`: Enable hot-reloading for server code development.

**Example:**
```bash
python prompt2render.py serve --host 127.0.0.1 --port 8787
```

---

## 3. 🚀 Master CLI: End-to-End Pipeline Execution

### `build` — Incremental Pipeline Builder
Runs the full pipeline (`voice` ➔ `align` ➔ `scenes` ➔ `stills` ➔ `plan` ➔ `encode` ➔ `finish` ➔ `publish` ➔ `check`). Every step caches results on disk; unmodified stages are skipped.

```bash
python prompt2render.py build <slug> [OPTIONS]
```

**Key Options:**
- `<slug>` *(Required)*: Project slug.
- `--manim`: Use Manim Community Edition instead of 2D SceneKit for scene generation.
- `--harness`: Execute build through the autonomous self-correction and evaluation harness.
- `--strict`: Enforce strict quality control gates (zero audio clipping, <42ms drift).
- `--config <path>`: Path to custom harness `config.yaml`.
- `--aspect {16:9, 9:16, 1:1, ...}`: Override video aspect ratio.
- `--voice <name>`: Voice name override (e.g. `af_heart`, `am_eric`).
- `--speed <float>`: Audio speech rate multiplier (e.g. `1.1`).
- `--lufs <float>`: Audio loudness target (default: `-14.0`).
- `--motion {none, dissolve, dissolve+reveal}`: Transition style.
- `--jobs <int>`: Parallel clip encoding workers (default: 1, or 3 on NVENC).
- `--scene-jobs <int>`: Concurrent Gemini storyboarding calls (default: 3).
- `--burn`: Hardcode / burn subtitle text directly onto video frames.
- `--hitl-mode {autonomous, human_on_failure, human_approval}`:
  - `autonomous` *(default)*: Auto-recovers or fails at gates.
  - `human_on_failure`: Drafts `hitl_review_needed.json` on hard gate failure.
  - `human_approval`: Blocks publishing until each section has an explicit accept in `hitl_feedback.json`.

**Example:**
```bash
python prompt2render.py build binary-search --manim --harness --strict
```

---

### `auto` — Fully Unattended Topic-to-Video Pipeline
Runs `new --ai` ➔ `draft` ➔ `build` unattended in a single command. Outlines sections, drafts narration with Gemini, synthesizes voice, renders animations, and verifies output.

```bash
python prompt2render.py auto <slug> [OPTIONS]
```

**Options:**
- `<slug>` *(Required)*: Project slug.
- `--title "<string>"`: Human-readable video title.
- `--minutes <float>`: Target duration for fresh project.
- `--sections <int>`: Target section count.
- `--redraft`: Re-draft narration even if sections already have written text.
- *Supports all flags from `build`* (`--manim`, `--harness`, `--strict`, `--config`, `--aspect`, `--voice`, `--speed`, `--lufs`, `--jobs`, `--hitl-mode`).

**Example:**
```bash
python prompt2render.py auto "dijkstra-algorithm" --title "Dijkstra's Algorithm" --minutes 3.0 --manim --harness --strict
```

---

## 4. 🧩 Master CLI: Modular Pipeline Stages

Use these individual stage commands to inspect, debug, or re-run specific parts of the workflow without running the entire pipeline.

### `draft` — AI Narration Draft
Prompts Gemini to draft natural narration in `script.md` for sections that are blank or placeholders.

```bash
python prompt2render.py draft <slug> [--force]
```
- `--force`: Overwrite existing narration sections.

---

### `voice` — Acoustic Narration Synthesis
Generates sample-exact audio per sentence using Kokoro-82M, concatenates into `master.wav`, and normalizes to `-14 LUFS`.

```bash
python prompt2render.py voice <slug> [OPTIONS]
```
**Options:**
- `--backend {kokoro, edge, own}`: Synthesis engine (`own` reads existing user audio files).
- `--voice <name>`: Voice name (e.g., `af_heart`, `am_eric`, `bf_alice`).
- `--speed <float>`: Speech playback speed multiplier.
- `--lufs <float>`: Target integrated loudness (default: `-14.0`).
- `--pause-sentence <ms>`: Inter-sentence pause duration in milliseconds.
- `--pause-paragraph <ms>`: Inter-paragraph pause duration in milliseconds.
- `--only <stem>`: Restrict synthesis to a single section stem (e.g. `--only 02`).
- `--force`: Force re-synthesis even if cached.

---

### `align` — Whisper Forced Alignment
Aligns rendered narration with the script text to extract word-level timestamps.

```bash
python prompt2render.py align <slug> [OPTIONS]
```
**Options:**
- `--only <stem>`: Align only the specified section stem.
- `--force`: Force re-alignment even if cached.
- `--no-asr`: Skip Whisper transcription; use exact TTS synthesis chunk timings.
- `--asr-jobs <int>`: Number of parallel transcription workers across section joins.

---

### `scenes` — Gemini Storyboarding & Scene Generation
Prompts Gemini to convert script section briefs (`> ANIM:`) into executable animation code.

```bash
python prompt2render.py scenes <slug> [OPTIONS]
```
**Options:**
- `--section <int>`: Storyboard only this section number (e.g. `--section 2`).
- `--retries <int>`: Maximum retry attempts if layout critic finds collisions (default: 0 = retry until pass).
- `--jobs <int>`: Number of concurrent section requests to Gemini API (default: 3).

---

### `stills` — SceneKit Frame Rasterization
Executes SceneKit python code and rasterizes frames to PNG images with pixel geometry auditing.

```bash
python prompt2render.py stills <slug> [OPTIONS]
```
**Options:**
- `--section <int>`: Render only this section number.
- `--check`: Audit layout geometry without writing PNG files to disk.
- `--force`: Force re-render even if stills are up-to-date.
- `--jobs <int>`: Concurrent section rendering workers.

---

### `plan` — Word-Synchronized Cut Planning
Computes frame-exact cut points and transition timestamps matching the audio timeline.

```bash
python prompt2render.py plan <slug> [OPTIONS]
```
**Options:**
- `--motion {none, dissolve, dissolve+reveal}`: Transition motion style.
- `--lead-ms <int>`: Milliseconds to advance visual transition ahead of spoken word (pre-roll cut).

---

### `encode` — Parallel Clip Encoding
Encodes video clips with dissolve heads using FFmpeg NVENC or libx264.

```bash
python prompt2render.py encode <slug> [OPTIONS]
```
**Options:**
- `--limit <int>`: Maximum clips to encode in this pass (resumable; default: 10).
- `--all`: Encode all pending clips in one pass.
- `--preview`: Fast NVENC pass for rapid inspection.
- `--jobs <int>`: Concurrent FFmpeg worker processes (default: 1, or 3 on NVENC).

---

### `finish` — Final Assembly & Multiplexing
Concatenates video clips, multiplexes 48kHz audio, generates chapters, and produces `out/final.mp4`.

```bash
python prompt2render.py finish <slug> [OPTIONS]
```
**Options:**
- `--burn`: Hardcode / burn captions directly into video stream.
- `--style {srt, ass}`: Subtitle style formatting (default: `srt`).

---

### `check` — Quality Control Gates
Runs automated quality gates against the finished video and audio.

```bash
python prompt2render.py check <slug> [--strict]
```
- `--strict`: Enforces strict thresholds (loudness within ±0.5 LUFS, zero clipped samples, caption drift <42ms).

---

### `publish` — Release Packet Generation
Generates YouTube upload assets in `projects/<slug>/out/`:
- `upload.md`: Formatted YouTube title, description, chapter timestamps, and tags.
- `thumbnail.png`: High-resolution video thumbnail.
- `attributions.md`: Creative Commons and open-source asset attributions.

```bash
python prompt2render.py publish <slug>
```

---

## 5. 🌐 Master CLI: Multilingual Video Generation

### `multilingual` — Multilingual Video from Prompt
Creates educational videos with native typography, complex text shaping, and formula preservation in English, Hindi, Urdu, Arabic, and Kashmiri.

```bash
python prompt2render.py multilingual "<prompt>" [OPTIONS]
```

**Options:**
- `<prompt>` *(Required)*: Educational prompt/topic in any language.
- `--lang <code/name>`: Target language (`en`, `hi`, `ur`, `ar`, `ks`; default: `en`).
- `--script <code>`: Target script (e.g. `Deva` or `Arab` for Kashmiri).
- `--input-lang <code>`: Prompt language (auto-detected if omitted).
- `--slug <slug>`: Project directory slug name.
- `--minutes <float>`: Target duration in minutes (default: 2.0).
- `--no-narration`: Disable TTS speech synthesis generation.
- `--no-subtitles`: Disable subtitle generation.

**Examples:**
```bash
# Hindi explainer on K-Means Clustering:
python prompt2render.py multilingual "K-Means Clustering Algorithm" --lang hi --minutes 3.0

# Urdu explainer on Binary Search:
python prompt2render.py multilingual "Binary Search Algorithm" --lang ur --minutes 2.5

# Kashmiri in Devanagari script:
python prompt2render.py multilingual "Newton's Laws of Motion" --lang ks --script Deva
```

---

## 6. 🛡️ Master CLI: Self-Correction & Harness Operations

These commands interact with the autonomous verification, evidence logging, and regression-safe repair system.

### `harness` — Run Standalone Harness Pipeline
Executes the plugin harness across all stages with structured logging and repair routing.

```bash
python prompt2render.py harness <slug> [--config <path>]
```

---

### `verify` — Deterministic Scene Verification
Performs deterministic layout, spatial, syntax, and timing verification on a single scene's current on-disk artifacts without invoking an LLM.

```bash
python prompt2render.py verify <slug> --section <n>
```
- `--section <int>` *(Required)*: Section number (e.g. `3` or `03`).

**Example:**
```bash
python prompt2render.py verify binary-search --section 3
```

---

### `repair` — Single-Scene Targeted Repair
Executes one regression-safe repair cycle: generates repair candidate ➔ renders ➔ re-verifies ➔ accepts or rolls back.

```bash
python prompt2render.py repair <slug> --section <n> [OPTIONS]
```
**Options:**
- `--section <int>` *(Required)*: Section number.
- `--manim`: Repair via Manim backend instead of SceneKit.
- `--config <path>`: Path to custom `config.yaml`.
- `--dry-run`: Evaluate repair candidate without committing changes to disk.

**Example:**
```bash
python prompt2render.py repair binary-search --section 3 --manim
```

---

### `rollback` — Restore Archived Revision
Restores a previous passing scene revision from `build/harness/revisions.json` as the active scene.

```bash
python prompt2render.py rollback <slug> --section <n> --revision <rev>
```
**Options:**
- `--section <int>` *(Required)*: Section number.
- `--revision <int>` *(Required)*: Revision number to restore (e.g. `1`).

---

### `replay` — Deterministic Re-render & Re-verify
Re-renders and re-verifies a scene deterministically from its current source file without calling Gemini.

```bash
python prompt2render.py replay <slug> --section <n>
```

---

### `scene-history` / `revisions` — Inspect Revision History
Prints the complete revision history, repair decisions, change contracts, and finding diffs for a scene.

```bash
python prompt2render.py scene-history <slug> --section <n>
# Alias:
python prompt2render.py revisions <slug> --section <n>
```

---

### `events` — Inspect Durable Build Event Journal
Queries `build/harness/events.jsonl` to trace lifecycle events (`scene.accepted`, `scene.rollback`, `harness.selfcheck`).

```bash
python prompt2render.py events <slug> [OPTIONS]
```
**Options:**
- `--scene <stem>`: Filter by scene stem (e.g. `--scene 03`).
- `--type <type>`: Filter by event type (e.g. `--type scene.rollback`).
- `--limit <int>`: Show only the last N events.
- `--json`: Output raw JSON records.

**Example:**
```bash
python prompt2render.py events binary-search --scene 03 --limit 5
```

---

### `harness-check` — Harness On-Disk Consistency Audit
Audits project disk artifacts against `revisions.json` and `manifest.json` without re-running any stages.

```bash
python prompt2render.py harness-check <slug>
```

---

### `report` — View Experiment Summary Report
Prints Section 19 experiment summary (repair cycles, scores, execution times, regression rate).

```bash
python prompt2render.py report <slug> [OPTIONS]
```
**Options:**
- `--json`: Output raw JSON data only.
- `--rebuild`: Recompute summary from current on-disk state instead of using cached summary.

---

### `ablation` — Run 4-Condition Detection-Only Ablation
Evaluates spatial and lifecycle verifiers across 4 combinations: `{spatial: off, lifecycle: off}`, `{on, off}`, `{off, on}`, `{on, on}`.

```bash
python prompt2render.py ablation <slug> [--config <path>] [--out <output.json>]
```

---

## 7. 🧰 Master CLI: Escape Hatches & Manual Overrides

### `import` — Import External Video Clips
Imports pre-rendered section MP4 clips from an external folder into `projects/<slug>/sections/`.

```bash
python prompt2render.py import <slug> <src_directory>
```

---

### `placeholders` — Generate Section Placeholders
Generates fallback title cards for any sections that have not yet been rendered.

```bash
python prompt2render.py placeholders <slug>
```

---

### `manim` — Render Standalone Hand-Authored Manim Scene
Renders a specific Manim scene class from an external python script and assigns it to a section index.

```bash
python prompt2render.py manim <slug> <pyfile> <scene_class> <index>
```
**Example:**
```bash
python prompt2render.py manim my-video scenes/custom_tree.py BinaryTreeScene 3
```

---

### `assemble` — Legacy Audio/Video Assembly
Assembles imported clips against `master.wav`, burns subtitles if requested, and produces `out/final.mp4`.

```bash
python prompt2render.py assemble <slug> [--burn]
```

---

## 8. 🔬 Standalone Diagnostic & Utility Scripts (`tools/`)

The `tools/` directory houses specialized utilities for research, testing, and batch processing:

### `tools/harness_run.py`
Standalone harness runner without executing `prompt2render.py`.
```bash
python tools/harness_run.py <slug> [--config path/to/config.yaml]
```

### `tools/ablation_runner.py`
Direct CLI entrypoint for Stage 5 Phase A detection-only ablation matrix.
```bash
python tools/ablation_runner.py --slug <slug> [--out results.json]
```

### `tools/audit_layout.py`
Tests the SceneKit layout critic against known good and bad layout geometries.
```bash
# Pass/fail summary:
python tools/audit_layout.py

# Also export debug frames as PNGs:
python tools/audit_layout.py --write debug_frames/
```

### `tools/golden_baseline.py`
Manages deterministic golden baseline tests for pipeline regressions.
```bash
# Record current baseline fixture:
python tools/golden_baseline.py record --slug hash-tables

# Verify against recorded baseline:
python tools/golden_baseline.py verify --slug hash-tables
```

### `tools/lung_infection_assets.py`
End-to-end integration test for external asset retrieval (Pixabay queries, download, vignette cropping, attributions).
```bash
python tools/lung_infection_assets.py
```

### `tools/build_kmeans_hindi.py`
Full production builder script for Hindi K-Means video project (script, TTS, scenes, and render).
```bash
python tools/build_kmeans_hindi.py
```

### `tools/generate_kmeans_scenes.py`
Generates Manim CE scene code for K-Means Hindi video.
```bash
python tools/generate_kmeans_scenes.py
```

### `tools/render_all_and_assemble.py`
Batch renders Manim scenes 01 to 07, normalizes durations to narration, concatenates, and muxes final video.
```bash
python tools/render_all_and_assemble.py
```

### `demo_self_correction.py`
Mock self-correction demonstration of `RepairController` (detect ➔ repair ➔ regression check ➔ rollback) without requiring API keys or rendering.
```bash
python demo_self_correction.py
```

### `test.py`
Standalone test scene file for Manim CE Scene09 (Vanishing Gradients).
```bash
manim -pql test.py Scene09
```

---

## 9. 🧪 Test Suite Execution (`pytest`)

Prompt2Render contains comprehensive test suites under `prompt2render/tests/`.

### Run All Tests
```bash
pytest
```

### Run Harness Tests Only
```bash
pytest prompt2render/tests/harness/
```

### Run Layout & Collision Critic Tests
```bash
pytest prompt2render/tests/test_qc_layout.py prompt2render/tests/test_manim_audit.py
```

### Run Multilingual Engine Tests
```bash
pytest prompt2render/tests/test_multilingual.py
```

### Run Audio & Foley Tests
```bash
pytest prompt2render/tests/test_audio_foley.py prompt2render/tests/test_align.py
```

### Run with Verbose Output & Stop on First Failure
```bash
pytest -v -x
```

---

## 10. 🐳 Setup, Environment & Docker Commands

### Windows Automated Setup (PowerShell)
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

### Activate Virtual Environment
```powershell
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Linux / macOS (Bash/Zsh):
source .venv/bin/activate
```

### Linux / macOS Automated Setup
```bash
chmod +x setup.sh
./setup.sh
```

### Dependency Installation (Manual)
```bash
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install "manim==0.21.0"
```

### Docker Compose
```bash
# Build container image:
docker compose build

# Start Prompt2Render studio container in background:
docker compose up -d

# View container logs:
docker compose logs -f

# Stop container:
docker compose down
```

---

## 11. ⚙️ Environment Variables & Performance Tuning

Configure these variables in your `.env` file or export them in your shell:

### API Keys
| Variable | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Primary Google Gemini API key (for storyboarding & drafting). |
| `GEMINI_API_KEY_BACKUP1` | Fallback key 1 for automatic rate-limit (429) failover. |
| `GEMINI_API_KEY_BACKUP2` | Fallback key 2 for automatic rate-limit (429) failover. |
| `PIXABAY_API_KEY` | API key for external stock image retrieval. |
| `PEXELS_API_KEY` | API key for external stock video retrieval. |
| `UNSPLASH_ACCESS_KEY` | API key for Unsplash photographic assets. |

### Engine & Hardware Tuning
| Variable | Default | Description |
| :--- | :--- | :--- |
| `P2R_RENDERER` | `scenekit` | Default visual engine (`scenekit` or `manim`). |
| `P2R_MANIM` | `0` | Set `1` to force Manim rendering mode. |
| `P2R_MANIM_VERSION` | `0.21.0` | Target Manim version check. |
| `P2R_VOICE` | `af_heart` | Default Kokoro TTS voice name. |
| `P2R_VOICE_JOBS` | `1` | Number of parallel voice synthesis processes. |
| `P2R_ASR_JOBS` | `1` | Concurrent Whisper forced-alignment workers. |
| `P2R_SCENE_JOBS` | `3` | Parallel Gemini storyboard requests. |
| `P2R_STILLS_JOBS` | CPU cores (max 4) | Parallel SceneKit frame rasterization workers. |
| `P2R_ENCODE_JOBS` | `3` (NVENC) / `1` (CPU) | Parallel FFmpeg clip encoding processes. |
| `P2R_MAX_SCENE_ATTEMPTS` | `0` (unlimited) | Cap retry attempts on scene critic failure. |
| `P2R_NO_CACHE` | `0` | Set `1` to bypass artifact caching and force rebuild. |
| `P2R_PNG_EXACT` | `0` | Enforce exact PNG rasterization rather than fast cached blit. |

---

## 12. 📋 Practical Workflows & Examples

### Workflow A: One-Shot Autonomous Video Generation (Manim)
```powershell
# 1. Ensure models and environment are ready
python prompt2render.py doctor
python prompt2render.py models --kokoro --asr base.en

# 2. Run end-to-end generation with strict quality gates
python prompt2render.py auto binary-search `
  --title "Binary Search Algorithm" `
  --minutes 3.0 `
  --manim `
  --harness `
  --strict
```

---

### Workflow B: Human-in-the-Loop (HITL) Manual Scene Tweaking
If section `03` has a visual collision or needs an artistic tweak:

1. Create or edit `projects/<slug>/hitl_feedback.json`:
```json
{
  "03": {
    "status": "reject",
    "reason": "The binary tree nodes collide with the title. Shift the tree root down by 1.5 units."
  }
}
```

2. Re-run the automated repair command:
```powershell
python prompt2render.py auto "<slug>" --harness --strict --manim
```
*The pipeline skips all passed sections (01, 02, 04...), re-prompts Gemini with your feedback only for section 03, re-renders the clip, and re-assembles `final.mp4`.*

3. Once accepted, clear or delete `hitl_feedback.json`.

---

### Workflow C: Single-Scene Rapid Repair & Verification
```powershell
# 1. Deterministically verify section 02
python prompt2render.py verify binary-search --section 2

# 2. Run one repair cycle on section 02 using Manim
python prompt2render.py repair binary-search --section 2 --manim

# 3. Check revision history
python prompt2render.py scene-history binary-search --section 2

# 4. If unsatisfied with repair, rollback to revision 1:
python prompt2render.py rollback binary-search --section 2 --revision 1
```

---

### Workflow D: Multilingual Educational Video (Hindi)
```powershell
# 1. Check supported languages & system fonts
python prompt2render.py languages

# 2. Generate Hindi video from topic prompt
python prompt2render.py multilingual "Introduction to Quantum Computing" `
  --lang hi `
  --minutes 2.5

# 3. Render and assemble with Manim
python prompt2render.py build intro-to-quantum-computing --manim --harness
```
