"""Serialize the script editor's in-browser model back to script.md,
shaped exactly like project.SCRIPT_TEMPLATE so project.parse_script()
round-trips it correctly on the next load.
"""
from __future__ import annotations


def render_script_md(meta: dict, sections: list[dict]) -> str:
    """meta: {"title": ..., "topic": ..., "audience": ..., ...}
    sections: [{"index": int, "title": str, "anim": str, "narration": str}, ...]
    """
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines += ["---", ""]

    for sec in sorted(sections, key=lambda s: s["index"]):
        idx = sec["index"]
        title = (sec.get("title") or f"Section {idx}").strip()
        anim = (sec.get("anim") or "").strip()
        narration = (sec.get("narration") or "").strip()
        lines.append(f"## {idx} - {title}")
        if anim:
            lines.append(f"> ANIM: {anim}")
        lines.append("")
        if narration:
            lines.append(narration)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
