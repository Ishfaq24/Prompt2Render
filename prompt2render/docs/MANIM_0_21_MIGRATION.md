# Manim 0.19.x -> 0.21.0 migration

## Supported version

`manimver.py` is the single source of truth. Default target: **0.21.0**.
Override with `P2R_MANIM_VERSION` (e.g. `P2R_MANIM_VERSION=0.19.0` to
reproduce the Code2Video comparison in `docs/MANIM_EXPERIMENT_PROTOCOL.md`).
Setting it re-targets the generator prompts, the static verifier's error
messages, and the render guard in `visuals.manim_scene()` /
`scenes._render_manim()` all at once — a mismatch between what's installed
and what's declared is reported, never silently ignored.

## Install

```
pip install "manim==0.21.0"
```

`requirements.txt` pins this by default; `setup.ps1`/`setup.sh` install
whatever `P2R_MANIM_VERSION` declares (default 0.21.0).

## Verify

```
prompt2render doctor                 # fast: reports installed vs. target version, LaTeX availability
prompt2render doctor --render-test   # slow: renders a real smoke scene, verifies 1920x1080 @ 30fps via ffprobe
P2R_MANIM_SMOKE=1 pytest prompt2render/tests/test_manim_smoke.py
```

Both the doctor render-test and the pytest smoke test share the same scene
and verification code (`manim_smoke.py`) so they can't drift apart.

## What actually changed between 0.19 and 0.21

Confirmed against the real installed 0.21.0 package (not just changelogs):

- **`Code` mobject — the one real breaking change.** `code=` and `style=`
  no longer exist.

  ```python
  # 0.19 (no longer works — raises TypeError)
  Code(code="x = 1", style="monokai", insert_line_numbers=True)

  # 0.21
  Code(
      code_string="x = 1",
      language="python",
      formatter_style="monokai",
      add_line_numbers=True,
      paragraph_config={"font_size": 24},   # font_size/color now live here
  )
  ```

  `scenes.py::validate_manim_source` flags `code=`, `style=`, a bare
  `font_size=`, `theme=`, and `insert_line_numbers=` on `Code(...)` with an
  actionable message; `scenes.py::_check_manim_kwarg_signatures` also
  catches any of these generically (and anything else invalid) via
  `inspect.signature` against whatever Manim is actually installed, so it
  stays correct even if the API moves again.

- **Everything else is unchanged**: `Text`, `MathTex`, `Tex` signatures; the
  `config` object's attribute surface (`pixel_width`, `frame_rate`,
  `media_dir`, `renderer`, ...); the CLI flags this project relies on
  (`-qh`, `--format mp4`, `--fps`, `-r W,H`, `--media_dir`,
  `--disable_caching`, bare `manim ...` aliasing to `manim render ...`).
  No render-command changes were needed.

## MathTex / Tex

Unchanged. Still requires a LaTeX install (`latex` or `pdflatex` on PATH);
`prompt2render doctor` reports this separately from the Manim version check.

## Typst

Manim 0.21 ships optional `Typst`/`MathTypst` mobjects (`pip install
"manim[typst]"`). **Not adopted.** MathTex over a LaTeX install remains the
supported math path; nothing in this project generates or expects Typst.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `doctor` warns "installed X, but this build targets Y" | `pip install "manim==Y"`, or set `P2R_MANIM_VERSION=X` if that's intentional |
| A hand-authored or LLM-generated scene uses old `Code(code=..., style=...)` | update to `code_string=`/`formatter_style=`; the static validator will flag it with the exact fix before it ever reaches Manim |
| `prompt2render doctor --render-test` fails but plain `doctor` shows LaTeX available | read the reported diagnostics — Manim's own stderr is surfaced verbatim; a common cause is a stale/incompatible LaTeX package rather than Manim itself |
| A section rendered under 0.19 looks unchanged after the upgrade but resumability keeps re-rendering it | check for stale `partial_movie_files` caches under `projects/<slug>/build/manim/**` from before the version bump — Manim's own cache is version/hash-sensitive; delete the section's `build/manim` cache subfolder and re-render if in doubt |
