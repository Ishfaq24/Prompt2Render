"""Unit and integration tests for external asset providers, preprocessor, and harness plugin."""

from __future__ import annotations

import json
from pathlib import Path
from PIL import Image
import pytest

from prompt2render.assets.cache import AssetCache
from prompt2render.assets.preprocessor import (
    apply_background_scrim,
    create_asset_card,
    crop_to_aspect_ratio,
    prepare_scene_asset,
)
from prompt2render.assets.providers.base import AssetHit
from prompt2render.assets.providers.mock import MockProvider
from prompt2render.assets.providers.pixabay import PixabayProvider
from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.retriever_external_asset import (
    RetrieverExternalAssetPlugin,
    _extract_asset_queries,
)
from prompt2render.publish import generate_attributions
from prompt2render import scenekit as k
import matplotlib.pyplot as plt


def test_mock_provider(tmp_path: Path):
    prov = MockProvider()
    assert prov.is_configured()
    hits = prov.search("cloud server", limit=2)
    assert len(hits) == 2
    assert hits[0].provider == "mock"
    assert "cloud" in hits[0].title.lower()

    dest = tmp_path / "test_download.png"
    result = prov.download(hits[0], dest)
    assert result.is_file()
    assert result.stat().st_size > 0

    with Image.open(result) as img:
        assert img.size == (1920, 1080)


def test_pixabay_provider_configured():
    prov = PixabayProvider()
    # If the user has PIXABAY_API_KEY in .env, it should be configured
    if prov.is_configured():
        hits = prov.search("computer", limit=2)
        assert len(hits) > 0
        assert hits[0].provider == "pixabay"
        assert hits[0].url.startswith("http")


def test_asset_cache(tmp_path: Path):
    cache = AssetCache(cache_dir=tmp_path / "cache")
    prov = MockProvider()
    hits = prov.search("database", limit=1)
    hit = hits[0]

    assert cache.get(hit) is None

    downloaded = cache.fetch_or_download(hit, prov)
    assert downloaded.is_file()

    # Second call hits cache
    cached = cache.get(hit)
    assert cached is not None
    assert cached == downloaded


def test_preprocessor(tmp_path: Path):
    # Create test raw image (4:3 aspect ratio)
    raw_path = tmp_path / "raw_4_3.png"
    img = Image.new("RGB", (800, 600), color=(100, 150, 200))
    img.save(raw_path)

    # 1. Background role (16:9 1920x1080 with scrim)
    bg_out = tmp_path / "bg.png"
    prepare_scene_asset(raw_path, bg_out, role="background")
    assert bg_out.is_file()
    with Image.open(bg_out) as bg_img:
        assert bg_img.size == (1920, 1080)

    # 2. Card role (960x540 with border)
    card_out = tmp_path / "card.png"
    prepare_scene_asset(raw_path, card_out, role="card", target_width=960, target_height=540)
    assert card_out.is_file()
    with Image.open(card_out) as card_img:
        assert card_img.size == (960, 540)


def test_query_extraction():
    queries = _extract_asset_queries(
        anim_text="ANIM: show a server rack with blinking lights",
        narration_text="DNS queries travel across the internet to reach the root nameserver.",
    )
    assert len(queries) >= 1
    found_queries = [q["query"] for q in queries]
    # Check if either anim words or dns metaphor matched
    assert any("server" in q for q in found_queries)


def test_retriever_external_asset_plugin(tmp_path: Path):
    proj_dir = tmp_path / "test_project"
    proj_dir.mkdir(parents=True)

    ctx = SceneContext(
        project_dir=proj_dir,
        scene_plan=[
            ScenePlanEntry(
                index=0,
                stem="01",
                title="DNS Hierarchy",
                anim="ANIM: DNS root nameserver",
                narration_text="When you type a domain into your browser, a DNS lookup begins.",
            )
        ],
    )

    plugin = RetrieverExternalAssetPlugin({"allow_mock_fallback": True, "max_assets_per_scene": 1})
    updated_ctx = plugin.run(ctx)

    assert "01" in updated_ctx.retrieval_context
    records = updated_ctx.retrieval_context["01"]
    assert len(records) >= 1
    assert "hint" in records[0]

    # Verify asset was staged to build/assets
    staged_dir = proj_dir / "build" / "assets"
    assert staged_dir.is_dir()
    staged_files = list(staged_dir.glob("01_*.png"))
    assert len(staged_files) >= 1

    # Verify provenance
    assert "01" in updated_ctx.asset_provenance
    assert len(updated_ctx.asset_provenance["01"]) >= 1


def test_retriever_external_asset_plugin_mock_fallback_when_real_providers_miss(tmp_path: Path, monkeypatch):
    from prompt2render.assets.providers.base import AssetProvider

    class EmptyRealProvider(AssetProvider):
        name = "empty_real"

        def is_configured(self) -> bool:
            return True

        def search(self, *args, **kwargs):
            return []

        def download(self, *args, **kwargs):
            raise NotImplementedError

    monkeypatch.setattr(
        "prompt2render.harness.plugins.retriever_external_asset.get_available_providers",
        lambda allow_mock_fallback=True: [EmptyRealProvider()],
    )

    proj_dir = tmp_path / "test_project_fallback"
    proj_dir.mkdir(parents=True)

    ctx = SceneContext(
        project_dir=proj_dir,
        scene_plan=[
            ScenePlanEntry(
                index=0,
                stem="01",
                title="Binary Search Range",
                anim="ANIM: binary search midpoint",
                narration_text="We divide the search space in half each step.",
            )
        ],
    )

    # When allow_mock_fallback is True, should fall back to mock without raising UnboundLocalError
    plugin = RetrieverExternalAssetPlugin({"allow_mock_fallback": True, "max_assets_per_scene": 1})
    updated_ctx = plugin.run(ctx)
    assert "01" in updated_ctx.retrieval_context
    assert len(updated_ctx.retrieval_context["01"]) >= 1
    assert updated_ctx.retrieval_context["01"][0]["provider"] == "mock"

    # When allow_mock_fallback is False, should not fall back to mock
    ctx_no_fallback = SceneContext(
        project_dir=proj_dir,
        scene_plan=[
            ScenePlanEntry(
                index=0,
                stem="02",
                title="Binary Search Range",
                anim="ANIM: binary search midpoint",
                narration_text="We divide the search space in half each step.",
            )
        ],
    )
    plugin_no_mock = RetrieverExternalAssetPlugin({"allow_mock_fallback": False, "max_assets_per_scene": 1})
    updated_ctx_no_mock = plugin_no_mock.run(ctx_no_fallback)
    assert "02" not in updated_ctx_no_mock.retrieval_context


def test_scenekit_draw_real_image(tmp_path: Path):
    test_img = tmp_path / "sample_asset.png"
    img = Image.new("RGB", (200, 200), color=(50, 100, 150))
    img.save(test_img)

    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_subplot(111)
    anchors = k.draw_asset(ax, str(test_img), x=8.0, y=4.5, width=4.0, height=3.0)
    plt.close(fig)

    assert "center" in anchors
    assert anchors["center"] == (8.0, 4.5)


def test_publish_attributions(tmp_path: Path):
    proj_dir = tmp_path / "proj"
    build_assets = proj_dir / "build" / "assets"
    build_assets.mkdir(parents=True)

    meta_file = build_assets / "01_test.meta.json"
    meta_file.write_text(
        json.dumps({
            "id": "pixabay_12345",
            "title": "Server Hardware",
            "author": "TechArtist",
            "author_url": "https://pixabay.com/users/tech",
            "provider": "pixabay",
            "license": "Pixabay Content License",
            "url": "https://pixabay.com/photos/12345",
        }),
        encoding="utf-8",
    )

    attrib_file = generate_attributions(proj_dir)
    assert attrib_file is not None
    assert attrib_file.is_file()
    content = attrib_file.read_text(encoding="utf-8")
    assert "TechArtist" in content
    assert "Pixabay" in content
    assert "Server Hardware" in content


def test_asset_provider_http_error_diagnostics(monkeypatch):
    import urllib.error
    from prompt2render.assets.providers.pexels import PexelsProvider

    warnings = []
    monkeypatch.setattr("prompt2render.cfg.warn", lambda msg: warnings.append(msg))

    def fake_urlopen_401(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.pexels.com", 401, "Unauthorized", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen_401)
    prov = PexelsProvider(api_key="invalid_key")
    hits = prov.search("technology")
    assert hits == []
    assert any("authentication failed (401)" in w for w in warnings)

    warnings.clear()

    def fake_urlopen_429(*args, **kwargs):
        raise urllib.error.HTTPError("https://pixabay.com", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen_429)
    pix_prov = PixabayProvider(api_key="rate_limited_key")
    pix_hits = pix_prov.search("robotics")
    assert pix_hits == []
    assert any("rate limit exceeded (429)" in w for w in warnings)

