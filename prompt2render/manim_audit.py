"""Runtime Manim spatial collision and bounding-box auditor.

Provides deterministic AABB (Axis-Aligned Bounding Box) collision detection,
caption boundary verification, and frame margin checks for rendered Manim
scenes and Mobjects before passing to VLM or final export.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ManimLayoutAuditor:
    """Evaluates spatial collision and bounds for Manim elements or frames."""

    # 16:9 canvas coordinates for Manim (standard units: width ~ 14.22, height ~ 8.0)
    X_MIN = -7.0
    X_MAX = 7.0
    Y_MIN = -4.0
    Y_MAX = 4.0

    # Layout safe boundaries
    TITLE_BAND_MIN_Y = 3.0
    CAPTION_CEILING_Y = -2.5

    @classmethod
    def audit_mobjects(
        cls,
        mobjects: list[Any],
        *,
        caption_mobjects: list[Any] | None = None,
        iou_threshold: float = 0.08,
    ) -> list[str]:
        """Audit a list of instantiated Manim Mobjects in a scene for collisions."""
        warnings: list[str] = []
        caption_set = set(caption_mobjects or [])

        # Extract bounding boxes: (x_min, y_min, x_max, y_max, name)
        boxes = []
        for i, mob in enumerate(mobjects):
            if mob in caption_set:
                continue
            if not hasattr(mob, "get_critical_point") and not hasattr(mob, "get_bounding_box"):
                continue
            try:
                # In Manim, points are [x, y, z]
                left = mob.get_left()[0]
                right = mob.get_right()[0]
                top = mob.get_top()[1]
                bottom = mob.get_bottom()[1]
                name = getattr(mob, "name", f"mobject_{i}")
                
                # Check canvas bounds
                if left < cls.X_MIN or right > cls.X_MAX or top > cls.Y_MAX or bottom < cls.Y_MIN:
                    warnings.append(
                        f"WARN [offframe] {name} [{left:.2f}, {bottom:.2f}, {right:.2f}, {top:.2f}] "
                        "extends past canvas boundaries"
                    )

                # Check caption zone trespass
                if bottom < cls.CAPTION_CEILING_Y:
                    warnings.append(
                        f"WARN [caption_collision] {name} bottom ({bottom:.2f}) "
                        f"trespasses into caption safe zone (y < {cls.CAPTION_CEILING_Y})"
                    )

                boxes.append((left, bottom, right, top, name, mob))
            except Exception:
                continue

        # Pairwise AABB Overlap check
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                l1, b1, r1, t1, n1, m1 = boxes[i]
                l2, b2, r2, t2, n2, m2 = boxes[j]

                # Check if one is a submobject of the other
                if hasattr(m1, "submobjects") and m2 in m1.submobjects:
                    continue
                if hasattr(m2, "submobjects") and m1 in m2.submobjects:
                    continue

                # AABB intersection
                inter_l = max(l1, l2)
                inter_b = max(b1, b2)
                inter_r = min(r1, r2)
                inter_t = min(t1, t2)

                if inter_r > inter_l and inter_t > inter_b:
                    inter_area = (inter_r - inter_l) * (inter_t - inter_b)
                    area1 = max(0.001, (r1 - l1) * (t1 - b1))
                    area2 = max(0.001, (r2 - l2) * (t2 - b2))
                    min_area = min(area1, area2)
                    union_area = area1 + area2 - inter_area
                    iou = inter_area / union_area if union_area > 0 else 0.0
                    iom = inter_area / min_area

                    # Ignore intentional container-child nesting (e.g. text in card)
                    is_container = (iom > 0.90) and (max(area1, area2) / min_area > 2.5)
                    if not is_container and (iou >= iou_threshold or iom >= 0.40):
                        warnings.append(
                            f"WARN [overlap] spatial overlap between {n1} and {n2} "
                            f"(IoU={iou:.2f}, IoM={iom:.2f})"
                        )

        return warnings

    @classmethod
    def auto_nudge_mobjects(
        cls,
        mobjects: list[Any],
        *,
        caption_mobjects: list[Any] | None = None,
        margin: float = 0.2,
        max_iterations: int = 5,
    ) -> int:
        """Deterministically nudge colliding Mobjects to resolve overlaps and caption trespass.
        
        Returns the number of resolved collisions/adjustments made without an LLM call.
        """
        import numpy as np
        caption_set = set(caption_mobjects or [])
        adjustments = 0

        for _ in range(max_iterations):
            moved = False
            # 1. Clamp caption safe zone violations
            for mob in mobjects:
                if mob in caption_set or not hasattr(mob, "get_bottom") or not hasattr(mob, "shift"):
                    continue
                try:
                    b_y = mob.get_bottom()[1]
                    min_allowed = cls.CAPTION_CEILING_Y + margin
                    if b_y < min_allowed:
                        delta_y = min_allowed - b_y
                        mob.shift(np.array([0.0, delta_y, 0.0]))
                        adjustments += 1
                        moved = True
                except Exception:
                    continue

            # 2. Pairwise overlap nudging
            for i in range(len(mobjects)):
                for j in range(i + 1, len(mobjects)):
                    m1 = mobjects[i]
                    m2 = mobjects[j]
                    if m1 in caption_set or m2 in caption_set:
                        continue
                    if not (hasattr(m1, "get_left") and hasattr(m2, "get_left") and hasattr(m2, "shift")):
                        continue

                    # Submobject relationship check
                    if hasattr(m1, "submobjects") and m2 in m1.submobjects:
                        continue
                    if hasattr(m2, "submobjects") and m1 in m2.submobjects:
                        continue

                    try:
                        l1, r1 = m1.get_left()[0], m1.get_right()[0]
                        b1, t1 = m1.get_bottom()[1], m1.get_top()[1]
                        l2, r2 = m2.get_left()[0], m2.get_right()[0]
                        b2, t2 = m2.get_bottom()[1], m2.get_top()[1]

                        inter_l = max(l1, l2)
                        inter_b = max(b1, b2)
                        inter_r = min(r1, r2)
                        inter_t = min(t1, t2)

                        if inter_r > inter_l and inter_t > inter_b:
                            # Collision detected! Compute minimum shift vector
                            overlap_x = inter_r - inter_l
                            overlap_y = inter_t - inter_b

                            # Nudge in the direction of smaller overlap
                            if overlap_y <= overlap_x:
                                if b2 < b1 and (b2 - overlap_y - margin) >= cls.CAPTION_CEILING_Y:
                                    m2.shift(np.array([0.0, -(overlap_y + margin), 0.0]))
                                elif hasattr(m1, "shift") and (t1 + overlap_y + margin) <= cls.Y_MAX:
                                    m1.shift(np.array([0.0, overlap_y + margin, 0.0]))
                                else:
                                    shift_x = (overlap_x + margin) if l2 >= l1 else -(overlap_x + margin)
                                    m2.shift(np.array([shift_x, 0.0, 0.0]))
                            else:
                                shift_x = (overlap_x + margin) if l2 >= l1 else -(overlap_x + margin)
                                m2.shift(np.array([shift_x, 0.0, 0.0]))

                            adjustments += 1
                            moved = True
                    except Exception:
                        continue

            if not moved:
                break

        return adjustments

    @classmethod
    def audit_rendered_clip(
        cls,
        clip_path: Path,
        section_timing: Any = None,
        scratch_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Convenience method wrapping visual_observe.observe_clip."""
        from . import visual_observe
        scratch = scratch_dir or clip_path.parent / ".audit_scratch"
        return visual_observe.observe_clip(
            clip_path,
            section_timing,
            scratch_dir=scratch,
        )
