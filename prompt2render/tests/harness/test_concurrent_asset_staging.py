"""Tests for concurrent idempotent asset staging across worker threads."""

from __future__ import annotations

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render.harness.plugins.retriever_asset_rag import stage_asset_safe


def test_concurrent_asset_staging(tmp_path: Path):
    """Verify that multiple concurrent threads staging the same asset file do not race."""
    src_file = tmp_path / "shared_cpu.svg"
    src_file.write_text("<svg><path d='M0 0 h10'/></svg>", encoding="utf-8")

    dest_dir = tmp_path / "build" / "assets"

    def _worker(thread_idx: int) -> Path:
        return stage_asset_safe(src_file, dest_dir)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        results = [f.result() for f in futures]

    assert len(results) == 20
    dest_file = dest_dir / "shared_cpu.svg"
    assert dest_file.is_file()
    assert dest_file.read_text(encoding="utf-8") == "<svg><path d='M0 0 h10'/></svg>"
