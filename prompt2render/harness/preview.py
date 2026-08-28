"""Robust preview-generation helper for Manim clips.

The harness's layout verifiers need a still image per scene to judge
caption overlap, safe-area violations etc. The renderer must guarantee
that ``scene.mp4`` AND a matching preview PNG are produced together
when layout verification requires the preview.

Before this module, ``visuals.manim_scene`` extracted the preview with:

    ffmpeg -sseof -0.1 -i dst -frames:v 1 preview.png

and silently swallowed every failure (``except: pass``). A failed
extraction left no file on disk, but downstream verifiers either
treated the missing preview as “no visual evidence” (skip) or crashed
with a raw ``FileNotFoundError`` that surfaced as a verifier exception
rather than a structured ``VERIFICATION_UNAVAILABLE`` finding. Both
hide the real problem and let a build proceed as if verification had
passed.

This module centralises the helper so:

* the filename is deterministic (``build/manim/previews/Scene<stem>.png``
  or a candidate-local variant when a repair candidate is open),
* existence and minimal size are verified after ffmpeg,
* stderr is captured for diagnostics,
* race conditions are avoided (temp file + atomic move),
* the caller receives an explicit success/failure rather than a silent
  ``None``,
* verifiers can map a failure to ``verification_unavailable`` instead of
  fabricating a PASS.

Scene number handling is independent of class-name assumptions: the stem
(``"01"``) is the single source of truth; the Manim class is expected
to be ``Scene<stem>`` but the preview path never inspects the class.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import SceneContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimal plausible preview size -- a 1920x1080 PNG that is smaller was
#: either truncated, empty, or a failed extraction that still happened to
#: create a file (ffmpeg can create a 0-byte output on some errors).
PREVIEW_MIN_BYTES = 1024

#: Canonical preview directory, relative to the project root.
PREVIEW_SUBDIR = Path("build") / "manim" / "previews"

#: Candidate-local preview subdir (under the sidecar root). Mirrors the
#: canonical layout so a candidate preview never overwrites the accepted
#: one -- the violation of atomic versioning that existed before this
#: module.
CANDIDATE_PREVIEW_SUBDIR = Path("previews")


def preview_path_for(context: "SceneContext", stem: str) -> Path:
    """Deterministic preview path for one scene, candidate-aware.

    While a repair candidate is open for ``stem`` the preview lives under
    that candidate's sidecar root so the accepted preview on disk is never
    clobbered before verification decides. Outside a candidate the
    canonical ``build/manim/previews/Scene<stem>.png`` is used.

    The stem is zero-padded to two digits for consistency (``"1"`` ->
    ``"01"``) but ``"01"`` itself is left unchanged. No class-name
    inspection is performed.
    """
    stem_str = str(stem).strip()
    # Normalise "7" -> "07", keep "07" as is, leave non-numeric stems
    # (e.g. "__all__") untouched -- they never have a preview anyway.
    try:
        stem_str = f"{int(stem_str):02d}"
    except (TypeError, ValueError):
        pass
    filename = f"Scene{stem_str}.png"

    # Candidate-aware: keep the preview isolated
    try:
        from . import workspace

        if workspace.is_candidate_open(context, stem_str):
            scope = context.candidate
            # ``scope`` is guaranteed to be for this stem when
            # ``is_candidate_open`` returned True.
            return Path(scope.root) / CANDIDATE_PREVIEW_SUBDIR / filename
        # Also handle legacy callers where ``stem`` was "1" but scope.stem
        # is "01" -- check the normalised form.
        if context.candidate is not None and workspace.is_candidate_open(
            context, context.candidate.stem
        ):
            # Fallback: if any candidate is open, check whether its stem
            # matches after normalisation. This avoids missing the case where
            # the caller passes "1" while the open candidate is "01".
            try:
                cand_stem_norm = f"{int(context.candidate.stem):02d}"
            except Exception:
                cand_stem_norm = str(context.candidate.stem)
            if cand_stem_norm == stem_str:
                return Path(context.candidate.root) / CANDIDATE_PREVIEW_SUBDIR / filename
    except Exception:
        pass

    project_dir = getattr(context, "project_dir", None)
    if project_dir is None:
        return Path(PREVIEW_SUBDIR) / filename
    return Path(project_dir) / PREVIEW_SUBDIR / filename


def canonical_preview_path(project_dir: Path | None, stem: str) -> Path:
    """Canonical preview path without needing a full SceneContext.

    Used by low-level utilities (``visuals.manim_scene``) that only have a
    ``project_dir`` and a stem. When a candidate sidecar is in use the
    caller should pass the explicit sidecar path instead -- this helper
    does not attempt to guess candidate state from a bare directory.
    """
    stem_str = str(stem).strip()
    try:
        stem_str = f"{int(stem_str):02d}"
    except (TypeError, ValueError):
        pass
    filename = f"Scene{stem_str}.png"
    if project_dir is None:
        return Path(PREVIEW_SUBDIR) / filename
    return Path(project_dir) / PREVIEW_SUBDIR / filename


def extract_preview(
    clip_path: Path,
    preview_path: Path,
    *,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Extract a single preview frame from ``clip_path`` to ``preview_path``.

    Returns ``(ok, diagnostics)``. ``ok`` is True only when the preview
    file exists afterwards **and** exceeds :data:`PREVIEW_MIN_BYTES`.
    Diagnostics contains ffmpeg stderr on failure (truncated) or an empty
    string on success. Never raises -- a failure is a verifiable fact,
    not an exception.

    Race safety: ffmpeg writes to a temporary file in the same directory
    which is then atomically moved onto the final destination, so a
    concurrent reader never sees a half-written file.
    """
    clip_path = Path(clip_path)
    preview_path = Path(preview_path)

    if not clip_path.exists():
        return False, f"clip not found at {clip_path}"

    preview_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file first, then move atomically.
    tmp_fd = None
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".png", dir=str(preview_path.parent), delete=False
        ) as tmp:
            tmp_fd = tmp.name
            tmp_path = Path(tmp_fd)
    except OSError as exc:
        return False, f"could not create temp file for preview: {exc}"

    assert tmp_path is not None

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-sseof",
                "-0.1",
                "-i",
                str(clip_path),
                "-frames:v",
                "1",
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        stderr = (result.stderr or result.stdout or "").strip()

        if result.returncode != 0:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            detail = f"ffmpeg exited {result.returncode}"
            if stderr:
                detail += f": {stderr[:800]}"
            return False, detail

        # Verify the temp file exists and is large enough
        if not tmp_path.exists():
            return False, "ffmpeg reported success but preview file is missing"

        try:
            size = tmp_path.stat().st_size
        except OSError as exc:
            return False, f"preview file could not be stat'd: {exc}"

        if size < PREVIEW_MIN_BYTES:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False, f"preview file too small ({size} bytes, need >{PREVIEW_MIN_BYTES})"

        # Atomic move onto final destination
        try:
            tmp_path.replace(preview_path)
        except OSError:
            # Cross-device fallback
            try:
                shutil.copyfile(tmp_path, preview_path)
                tmp_path.unlink(missing_ok=True)
            except OSError as exc:
                return False, f"could not move preview into place: {exc}"
            # Also verify the final path now exists and is large enough
            try:
                final_size = preview_path.stat().st_size
                if final_size < PREVIEW_MIN_BYTES:
                    return False, f"final preview too small ({final_size} bytes)"
            except OSError as exc:
                return False, f"final preview not readable: {exc}"

        return True, stderr

    except subprocess.TimeoutExpired:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"preview extraction timed out after {timeout}s"
    except FileNotFoundError:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False, "ffmpeg not found on PATH"
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"preview extraction failed: {exc}"
    finally:
        # Defensive cleanup of any leftover temp file if we didn't move it
        if tmp_path is not None and tmp_path.exists() and tmp_path != preview_path:
            # Only clean if we haven't already moved it (move would have
            # removed the tmp file on same-device replace, but not on
            # copyfile fallback where we already unlinked)
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def ensure_preview(
    context: "SceneContext",
    stem: str,
    clip_path: Path | None = None,
) -> tuple[Path | None, str]:
    """Ensure a preview exists for ``stem``, extracting if needed.

    When ``clip_path`` is None the clip is resolved from the render
    artifact (candidate-aware). Returns ``(preview_path, diagnostics)``.
    ``preview_path`` is the path that now exists (or ``None`` if
    extraction failed). ``diagnostics`` is empty on success, or a
    human-readable reason on failure suitable for a
    ``verification_unavailable`` finding's ``reason`` field.

    Never raises.
    """
    try:
        preview_path = preview_path_for(context, stem)
    except Exception as exc:
        return None, f"could not resolve preview path for {stem}: {exc}"

    # If it already exists and is fresh + large enough, reuse it.
    if preview_path.exists():
        try:
            size = preview_path.stat().st_size
            if size >= PREVIEW_MIN_BYTES:
                # Freshness check: preview should be >= clip mtime when
                # we have a clip to compare against.
                if clip_path is not None:
                    try:
                        if preview_path.stat().st_mtime >= Path(clip_path).stat().st_mtime:
                            return preview_path, ""
                        # Stale preview -- fall through to re-extract
                    except OSError:
                        pass
                else:
                    # Try to resolve clip for freshness
                    try:
                        artifact = context.render_artifacts.get(str(stem).strip())
                        if artifact is not None and hasattr(artifact, "clip_path"):
                            cpath = artifact.clip_path()
                            if cpath is not None and Path(cpath).exists():
                                if preview_path.stat().st_mtime >= Path(cpath).stat().st_mtime:
                                    return preview_path, ""
                    except Exception:
                        pass
                    return preview_path, ""
                # If freshness unknown, still return existing file
                return preview_path, ""
        except OSError:
            pass
        # Size too small or stat failed -- re-extract

    # Resolve clip if not given
    if clip_path is None:
        try:
            artifact = context.render_artifacts.get(str(stem).strip())
            if artifact is not None:
                clip = artifact.clip_path() if hasattr(artifact, "clip_path") else getattr(artifact, "clip", None)
                if clip is not None:
                    clip_path = Path(clip)
        except Exception:
            clip_path = None

        if clip_path is None:
            # Fallback to canonical sections/NN.mp4 or build/manim search
            try:
                project_dir = getattr(context, "project_dir", None)
                if project_dir is not None:
                    # Try workspace candidate clip first
                    try:
                        from . import workspace

                        if workspace.is_candidate_open(context, stem):
                            cand_clip = Path(context.candidate.render_dir) / f"{int(stem):02d}.mp4"
                            if cand_clip.exists():
                                clip_path = cand_clip
                    except Exception:
                        pass
                    if clip_path is None:
                        cand = Path(project_dir) / "sections" / f"{int(stem):02d}.mp4"
                        if cand.exists():
                            clip_path = cand
                        else:
                            from ..visuals import latest_manim_clip

                            clip_path = latest_manim_clip(Path(project_dir), str(stem).strip())
            except Exception:
                pass

    if clip_path is None or not Path(clip_path).exists():
        return None, f"required preview artifact missing -- no rendered clip found for scene {stem!r} to extract preview from"

    ok, diagnostics = extract_preview(Path(clip_path), preview_path)
    if ok:
        return preview_path, diagnostics
    return None, diagnostics


__all__ = [
    "PREVIEW_MIN_BYTES",
    "PREVIEW_SUBDIR",
    "CANDIDATE_PREVIEW_SUBDIR",
    "preview_path_for",
    "canonical_preview_path",
    "extract_preview",
    "ensure_preview",
]
