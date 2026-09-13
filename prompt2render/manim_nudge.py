"""Source-level deterministic Manim layout nudger.

Applies geometry fixes to generated Manim Python source without executing it.
Catches the top-3 overlap patterns that survive validation and appear in rendered output:

  1. Parallel DOWN anchoring  — two items anchored to the same parent with next_to(parent, DOWN)
                                 → chains them so item2.next_to(item1, DOWN)
  2. Same-y crowding          — two move_to calls at identical y < 1.0 with close x
                                 → shifts the second element 0.9 units down
  3. Caption zone trespass    — non-caption element at y < -2.4
                                 → clamped to y = -2.2

All fixes are applied in a single pass and are idempotent.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Pattern 1: parallel DOWN anchoring
# ---------------------------------------------------------------------------

_NEXT_TO_DOWN = re.compile(
    r'^(\s*)(\w+)\.next_to\(\s*(\w+)\s*,\s*DOWN\b([^)]*)\)',
    re.MULTILINE,
)


def _fix_parallel_down_anchoring(code: str) -> tuple[str, int]:
    """Chain sibling next_to(anchor, DOWN) calls so they don't stack on top of each other."""
    lines = code.splitlines()
    anchors: dict[str, str] = {}   # anchor_name -> last_placed_child
    new_lines: list[str] = []
    fixes = 0

    for line in lines:
        m = re.match(
            r'^(\s*)(\w+)\.next_to\(\s*(\w+)\s*,\s*DOWN\b([^)]*)\)',
            line,
        )
        if m:
            indent, child, anchor, extra = m.groups()
            if anchor in anchors and anchors[anchor] != child:
                prev = anchors[anchor]
                line = f"{indent}{child}.next_to({prev}, DOWN, buff=0.3)"
                fixes += 1
            anchors[anchor] = child
        else:
            # Reset anchor tracking on non-next_to lines to avoid
            # cross-block false matches
            if re.match(r'^\s*$', line) or re.match(r'^\s*(self\.play|self\.wait|#)', line):
                anchors.clear()
        new_lines.append(line)

    return "\n".join(new_lines), fixes


# ---------------------------------------------------------------------------
# Pattern 2: same-y crowding
# ---------------------------------------------------------------------------

_MOVE_TO_COORD = re.compile(
    r'(\b\w+)\.move_to\(\s*np\.array\(\[([\d.eE+\-]+)\s*,\s*([\d.eE+\-]+)\s*,',
)
_MOVE_TO_TUPLE = re.compile(
    r'(\b\w+)\.move_to\(\s*\(\s*([\d.eE+\-]+)\s*,\s*([\d.eE+\-]+)\s*,',
)


def _fix_same_y_crowding(code: str) -> tuple[str, int]:
    """Offset two non-caption elements placed at exactly the same y-coordinate."""
    # Build a map: y_value -> [(var_name, line_index, full_match_text)]
    placed: dict[float, list[tuple[str, int, str]]] = {}
    lines = code.splitlines()
    fixes = 0

    for i, line in enumerate(lines):
        for pat in (_MOVE_TO_COORD, _MOVE_TO_TUPLE):
            m = pat.search(line)
            if not m:
                continue
            varname = m.group(1)
            if any(kw in varname.lower() for kw in ("caption", "sub", "title")):
                continue
            try:
                x_val = float(m.group(2))
                y_val = float(m.group(3))
            except ValueError:
                continue
            key = round(y_val, 2)
            if key not in placed:
                placed[key] = []
            placed[key].append((varname, i, line))

    for y_val, items in placed.items():
        if len(items) < 2:
            continue
        # Only fix when x values are close (within 2.5 units)
        for idx in range(1, len(items)):
            prev_x = 0.0
            curr_x = 0.0
            try:
                for pat in (_MOVE_TO_COORD, _MOVE_TO_TUPLE):
                    pm = pat.search(items[idx - 1][2])
                    cm = pat.search(items[idx][2])
                    if pm and cm:
                        prev_x = float(pm.group(2))
                        curr_x = float(cm.group(2))
                        break
            except (ValueError, TypeError):
                continue

            if abs(prev_x - curr_x) < 2.5:
                line_i = items[idx][1]
                new_y = y_val - 0.9
                # Replace the y value in that specific line
                original = lines[line_i]
                patched = re.sub(
                    r'(\.move_to\(\s*(?:np\.array\(\[|\()\s*[\d.eE+\-]+\s*,\s*)([\d.eE+\-]+)(\s*,)',
                    lambda mo: mo.group(1) + f"{new_y:.2f}" + mo.group(3),
                    original,
                    count=1,
                )
                if patched != original:
                    lines[line_i] = patched
                    fixes += 1

    return "\n".join(lines), fixes


# ---------------------------------------------------------------------------
# Pattern 3: caption zone trespass
# ---------------------------------------------------------------------------

_MOVE_TO_NEG_Y = re.compile(
    r'(\b(\w+))\.move_to\(\s*\(\s*([\d.eE+\-]+)\s*,\s*(-[3-9](?:\.\d+)?)\s*(?:,\s*[^)]*)?\)\s*\)'
)


def _fix_caption_zone_trespass(code: str) -> tuple[str, int]:
    """Clamp non-caption/subtitle elements that trespass into y < -2.4."""
    fixes = 0

    def _replacer(m: re.Match) -> str:
        nonlocal fixes
        full_name = m.group(2).lower()
        if any(kw in full_name for kw in ("caption", "sub", "title", "label")):
            return m.group(0)
        x_val = m.group(3)
        fixes += 1
        return f"{m.group(1)}.move_to(({x_val}, -2.2, 0))"

    return _MOVE_TO_NEG_Y.sub(_replacer, code), fixes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def nudge_source(code: str) -> tuple[str, int]:
    """Apply deterministic layout fixes to generated Manim source.

    Runs three passes in order:
      1. Parallel DOWN anchoring chains
      2. Same-y crowding offsets
      3. Caption zone trespass clamp

    Returns:
        (patched_code, total_fixes_applied)
        If total_fixes == 0 the source was already clean and is returned unchanged.
    """
    total = 0
    patched, n = _fix_parallel_down_anchoring(code)
    total += n
    patched, n = _fix_same_y_crowding(patched)
    total += n
    patched, n = _fix_caption_zone_trespass(patched)
    total += n
    if total == 0:
        return code, 0
    if code.endswith("\n") and not patched.endswith("\n"):
        patched += "\n"
    return patched, total
