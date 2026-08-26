"""Shared safe-zone abstraction for Prompt2Render.

This module is the single authoritative definition of the frame's
structural zones. Both backends (SceneKit/matplotlib and Manim) derive
their geometry from the same conceptual tiling rather than scattering
magic numbers through generated scene code.

Conceptually:

    TITLE
    ----------------
    VISUAL
    ----------------
    SUPPORTING LABELS
    ----------------
    CAPTION
    ----------------

For SceneKit (matplotlib) the canvas is a fixed 16 x 9 unit grid at
1920x1080 (see scenekit.W, scenekit.H, scenekit.PX_W/H). For Manim the
canvas size is config.frame_width / config.frame_height (≈14.22 x 8)
with SAFE_MARGIN in Manim units (see manim_contract.LAYOUT_PREAMBLE).

Both define the same four zones as intervals on the Y axis; the X axis
is bounded by the safe margins.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# SceneKit (matplotlib) zones -- units are scenekit.W/H (16 x 9)
# ---------------------------------------------------------------------------

SCENEKIT_W = 16.0
SCENEKIT_H = 9.0
SCENEKIT_PX_W = 1920
SCENEKIT_PX_H = 1080
SCENEKIT_MARGIN_PX = 12

# Mirrors the layout rules already documented in scenes.API_DOC / scenekit.title
SCENEKIT_ZONES = {
    # y=7.6..8.6 title band (title() at y=8.1, size 46)
    "title": (7.6, 8.6),
    # y=4.0..7.0 primary visualization (arrays, trees, code panels)
    "visual": (4.0, 7.0),
    # y=1.5..3.5 secondary (pointers, variables, comparisons)
    "secondary": (1.5, 3.5),
    # y=0.4..1.3 caption zone (caption() at y=0.85)
    "caption": (0.4, 1.3),
}

# Additional derived: safe margins in units
SCENEKIT_SAFE_X = (0.4, 15.6)  # x in [0.4, 15.6]
SCENEKIT_SAFE_Y = (0.4, 8.6)   # y in [0.4, 8.6]

# Thresholds
SCENEKIT_CAPTION_MAX_HEIGHT_UNITS = 0.95  # caption band height ≈0.9
SCENEKIT_LABEL_CAPTION_GAP_PX = 18  # minimum gap between caption and nearest label
SCENEKIT_NEAR_MARGIN_PX = 20  # WARNING threshold (close to edge but not out)
SCENEKIT_OVERLAP_MIN_PX2 = 60.0


@dataclass(frozen=True)
class Zone:
    """One horizontal band."""

    name: str
    y_min: float
    y_max: float

    @property
    def center(self) -> float:
        return (self.y_min + self.y_max) / 2

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def contains(self, y: float) -> bool:
        return self.y_min <= y <= self.y_max

    def overlaps(self, y0: float, y1: float) -> bool:
        """Whether interval [y0, y1] overlaps this zone."""
        lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
        return max(lo, self.y_min) < min(hi, self.y_max)


SCENEKIT_ZONE_OBJECTS: dict[str, Zone] = {
    name: Zone(name, y0, y1) for name, (y0, y1) in SCENEKIT_ZONES.items()
}

# ---------------------------------------------------------------------------
# Manim zones -- derived from manim_contract.LAYOUT_PREAMBLE constants
# ---------------------------------------------------------------------------
# These mirror the preamble's band arithmetic so generated code and verifier
# agree byte-for-byte. Values are in Manim units (≈14.22 x 8).
# Preamble:
#   SAFE_MARGIN_X = 0.45, SAFE_MARGIN_Y = 0.35
#   BAND_GUTTER = 0.25
#   TITLE_MAX_HEIGHT = 0.9
#   CAPTION_MAX_HEIGHT = 1.1
#   TITLE_Y = SAFE_TOP - TITLE_MAX_HEIGHT/2
#   CAPTION_Y = SAFE_BOTTOM + CAPTION_MAX_HEIGHT/2
#   CONTENT_TOP = SAFE_TOP - TITLE_MAX_HEIGHT - BAND_GUTTER
#   CONTENT_BOTTOM = SAFE_BOTTOM + CAPTION_MAX_HEIGHT + BAND_GUTTER

MANIM_SAFE_MARGIN_X = 0.45
MANIM_SAFE_MARGIN_Y = 0.35
MANIM_BAND_GUTTER = 0.25
MANIM_TITLE_MAX_HEIGHT = 0.9
MANIM_CAPTION_MAX_HEIGHT = 1.1

# Helper: these are relative to config.frame_width/height, so we cannot
# compute absolute SAFE_TOP etc without runtime config. Instead we store
# the band definitions as offsets.

MANIM_ZONES_FRACTIONAL = {
    # Fractional position within safe height (0=bottom of safe area, 1=top)
    # Caption: bottom 0 .. 1.1 / SAFE_HEIGHT
    # Title: top 1 - 0.9/SAFE_HEIGHT .. 1
    # We expose helpers that compute actual coordinates given frame size.
    "caption_height": MANIM_CAPTION_MAX_HEIGHT,
    "title_height": MANIM_TITLE_MAX_HEIGHT,
    "gutter": MANIM_BAND_GUTTER,
}


def manim_zones(frame_w: float = 14.222, frame_h: float = 8.0) -> dict[str, tuple[float, float]]:
    """Return Manim Y zones for a given frame size.

    Returns {name: (y_min, y_max)} in Manim coordinates (origin center).
    """
    safe_top = frame_h / 2 - MANIM_SAFE_MARGIN_Y
    safe_bottom = -frame_h / 2 + MANIM_SAFE_MARGIN_Y
    safe_height = safe_top - safe_bottom

    title_top = safe_top
    title_bottom = safe_top - MANIM_TITLE_MAX_HEIGHT
    caption_bottom = safe_bottom
    caption_top = safe_bottom + MANIM_CAPTION_MAX_HEIGHT
    content_top = safe_top - MANIM_TITLE_MAX_HEIGHT - MANIM_BAND_GUTTER
    content_bottom = safe_bottom + MANIM_CAPTION_MAX_HEIGHT + MANIM_BAND_GUTTER

    return {
        "title": (title_bottom, title_top),
        "content": (content_bottom, content_top),
        "caption": (caption_bottom, caption_top),
        # Keep conceptual secondary band as lower half of content
        "secondary": (content_bottom, (content_bottom + content_top) / 2),
        "safe": (safe_bottom, safe_top),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scenekit_caption_zone() -> Zone:
    return SCENEKIT_ZONE_OBJECTS["caption"]


def scenekit_title_zone() -> Zone:
    return SCENEKIT_ZONE_OBJECTS["title"]


def is_valid_category(category: str) -> bool:
    return category in {"LAYOUT", "SPATIAL", "SEMANTIC", "TEMPORAL", "PEDAGOGY", "STRUCTURAL", "CODE", "RENDER"}


__all__ = [
    "SCENEKIT_W",
    "SCENEKIT_H",
    "SCENEKIT_PX_W",
    "SCENEKIT_PX_H",
    "SCENEKIT_MARGIN_PX",
    "SCENEKIT_ZONES",
    "SCENEKIT_SAFE_X",
    "SCENEKIT_SAFE_Y",
    "SCENEKIT_CAPTION_MAX_HEIGHT_UNITS",
    "SCENEKIT_LABEL_CAPTION_GAP_PX",
    "SCENEKIT_NEAR_MARGIN_PX",
    "SCENEKIT_OVERLAP_MIN_PX2",
    "SCENEKIT_ZONE_OBJECTS",
    "MANIM_SAFE_MARGIN_X",
    "MANIM_SAFE_MARGIN_Y",
    "MANIM_BAND_GUTTER",
    "MANIM_TITLE_MAX_HEIGHT",
    "MANIM_CAPTION_MAX_HEIGHT",
    "MANIM_ZONES_FRACTIONAL",
    "Zone",
    "manim_zones",
    "scenekit_caption_zone",
    "scenekit_title_zone",
]
