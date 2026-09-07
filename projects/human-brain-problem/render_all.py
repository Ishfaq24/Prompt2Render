import subprocess
import sys
from pathlib import Path

scenes = [
    ("01", "Scene01"),
    ("02", "Scene02"),
    ("03", "Scene03"),
    ("04", "Scene04"),
    ("05", "Scene05"),
    ("06", "Scene06"),
]


base_dir = Path("projects/human-brain-problem")
scene_dir = base_dir / "build" / "scenes"

for stem, scene_cls in scenes:
    py_file = scene_dir / f"scene_{stem}.py"
    out_name = f"scene_{stem}.mp4"
    cmd = [
        sys.executable,
        "-m", "manim",
        "-qh",
        "--disable_caching",
        "-o", out_name,
        str(py_file),
        scene_cls,
    ]
    print(f"=== Rendering {stem} ({scene_cls}) ===")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print(f"Error rendering {stem}")
        sys.exit(res.returncode)

print("All scenes rendered successfully!")
