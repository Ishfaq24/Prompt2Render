"""Detailed end-to-end test script for external asset retrieval on 'Lungs Infection'.

Exercises:
1. Scene script definition for 'lung-infection'.
2. Query extraction and live Pixabay API search using PIXABAY_API_KEY.
3. Download and caching.
4. Preprocessing (16:9 center crop, dark vignette background, reference card).
5. Staging into `projects/lung-infection/build/assets/`.
6. Rendering a preview scene frame with scenekit (k.draw_asset).
7. License attribution generation into `projects/lung-infection/out/attributions.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt2render import cfg, scenekit as k
from prompt2render.assets.cache import AssetCache
from prompt2render.assets.preprocessor import prepare_scene_asset
from prompt2render.assets.providers.pixabay import PixabayProvider
from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.retriever_external_asset import (
    RetrieverExternalAssetPlugin,
    _extract_asset_queries,
)
from prompt2render.publish import generate_attributions

import matplotlib.pyplot as plt
from PIL import Image


def main():
    print("=" * 70)
    print("PROMPT2RENDER — DETAILED EXTERNAL ASSET TEST: LUNGS INFECTION")
    print("=" * 70)

    cfg.load_env()
    proj_dir = ROOT / "projects" / "lung-infection"
    proj_dir.mkdir(parents=True, exist_ok=True)
    build_dir = proj_dir / "build"
    build_assets = build_dir / "assets"
    build_scenes = build_dir / "scenes"
    out_dir = proj_dir / "out"
    build_assets.mkdir(parents=True, exist_ok=True)
    build_scenes.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Define sample script for Lungs Infection
    script_md = proj_dir / "script.md"
    script_content = """---
title: Understanding Lung Infections: From Pathogens to Pneumonia
topic: lung infection, respiratory system, pneumonia, alveoli, immune response
audience: general educational
---

## 1 - The Respiratory Anatomy
> ANIM: detailed anatomical structure of healthy human lungs and trachea

The human respiratory system draws oxygen deep into our lungs through a branching network of bronchial tubes, leading to millions of tiny air sacs called alveoli.

## 2 - Bacterial and Viral Invasion
> ANIM: microscope view of bacteria and virus infecting lung tissue and alveoli

When pathogens such as bacteria or viruses bypass our airways, they settle in the alveoli, causing acute inflammation and fluid buildup commonly known as pneumonia.

## 3 - The Immune Defense
> ANIM: white blood cells attacking pathogens in the pulmonary capillaries

In response to the infection, our immune system mobilizes white blood cells and antibodies to neutralize the invaders and restore healthy respiratory function.
"""
    script_md.write_text(script_content, encoding="utf-8")
    print(f"\n[1] Prepared project script at: {script_md}")

    # 2. Check Pixabay Provider
    pix = PixabayProvider()
    print(f"[2] Pixabay Provider configured: {pix.is_configured()}")
    if not pix.is_configured():
        print("    Warning: PIXABAY_API_KEY not found in environment or .env.")

    # 3. Create SceneContext with the 3 sections
    plan_entries = [
        ScenePlanEntry(
            index=0,
            stem="01",
            title="The Respiratory Anatomy",
            anim="ANIM: detailed anatomical structure of healthy human lungs and trachea",
            narration_text="The human respiratory system draws oxygen deep into our lungs through a branching network of bronchial tubes.",
        ),
        ScenePlanEntry(
            index=1,
            stem="02",
            title="Bacterial and Viral Invasion",
            anim="ANIM: microscope view of bacteria and virus infecting lung tissue and alveoli",
            narration_text="When pathogens such as bacteria or viruses bypass our airways, they settle in the alveoli, causing acute inflammation.",
        ),
        ScenePlanEntry(
            index=2,
            stem="03",
            title="The Immune Defense",
            anim="ANIM: white blood cells attacking pathogens in the pulmonary capillaries",
            narration_text="In response to the infection, our immune system mobilizes white blood cells to neutralize invaders.",
        ),
    ]

    context = SceneContext(project_dir=proj_dir, scene_plan=plan_entries)

    # 4. Run RetrieverExternalAssetPlugin
    print("\n[3] Running RetrieverExternalAssetPlugin...")
    plugin = RetrieverExternalAssetPlugin({"max_assets_per_scene": 1, "allow_mock_fallback": False})
    updated_context = plugin.run(context)

    print("\n[4] Retrieval Context Results:")
    for stem, records in updated_context.retrieval_context.items():
        print(f"\n  --- Section {stem} ---")
        for rec in records:
            print(f"  * Asset ID:    {rec.get('id')}")
            print(f"  * Title:       {rec.get('name')}")
            print(f"  * Provider:    {rec.get('provider')} (by {rec.get('author')})")
            print(f"  * Staged File: {rec.get('staged_path')}")
            print(f"  * Role:        {rec.get('role')}")

    # 5. Verify Staged Files on Disk
    staged_files = sorted(build_assets.glob("*.png"))
    print(f"\n[5] Staged Asset Files on Disk ({len(staged_files)} total):")
    for f in staged_files:
        with Image.open(f) as img:
            size_str = f"{img.size[0]}x{img.size[1]}"
        print(f"  * {f.name} ({size_str}, {f.stat().st_size // 1024} KB)")

    # 6. Render a visual test scene using scenekit k.draw_asset with the staged image!
    print("\n[6] Rendering test scene with SceneKit (k.draw_asset)...")
    bacteria_assets = [f for f in staged_files if "123081" in f.name or "bacteria" in f.name]
    test_asset_path = bacteria_assets[0] if bacteria_assets else staged_files[0]
    if test_asset_path:
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("#0d1117")
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 9)
        ax.axis("off")

        # Draw Title
        k.title(ax, "Alveolar Infection: Bacterial Colonization & Pneumonia", y=8.2, size=32)

        # Draw the real photo using draw_asset
        k.draw_asset(ax, str(test_asset_path), x=5.0, y=4.5, width=6.5, height=4.2, color="#f85149")

        # Draw diagram labels and blocks beside it
        k.block(ax, "BACTERIAL PROLIFERATION\nEscherichia coli & Streptococcus", 12.0, 6.0, w=5.2, h=1.8, active=True, size=18)
        k.block(ax, "ALVEOLAR CONSOLIDATION\nInflammatory exudate & fluid fills sacs", 12.0, 3.2, w=5.2, h=1.8, active=False, size=18)

        # Connect callout arrows
        k.arrow(ax, 8.3, 6.0, 9.4, 6.0, color="#f85149")
        k.arrow(ax, 8.3, 3.2, 9.4, 3.2, color="#d29922")

        preview_out = build_scenes / "preview_lung_infection.png"
        fig.savefig(preview_out, facecolor="#0d1117", dpi=100)
        plt.close(fig)
        print(f"  -> Generated test scene preview: {preview_out}")

    # 7. Generate Media Attributions
    print("\n[7] Generating Media Attributions & Licensing...")
    attrib_file = generate_attributions(proj_dir)
    if attrib_file and attrib_file.exists():
        print(f"  -> Generated: {attrib_file}")
        print("\n" + attrib_file.read_text(encoding="utf-8"))

    print("=" * 70)
    print("SUCCESS: Lung Infection external asset pipeline test completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
