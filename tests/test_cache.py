"""Tests for cache list/prune helpers."""

import time
from pathlib import Path

from yt_tools.cache import cache_list, cache_prune


def _touch(path: Path, mtime_offset_days: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime_offset_days:
        ts = time.time() - mtime_offset_days * 86400
        import os
        os.utime(path, (ts, ts))
        os.utime(path.parent, (ts, ts))


def test_cache_list_empty(tmp_path: Path):
    entries = cache_list(tmp_path / "yt-cache")
    assert entries == []


def test_cache_list_finds_video_dirs(tmp_path: Path):
    cache_root = tmp_path / "yt-cache"
    _touch(cache_root / "abc12345" / "source.mp4")
    _touch(cache_root / "xyz67890" / "transcript.md")
    entries = cache_list(cache_root)
    ids = sorted(e.video_id for e in entries)
    assert ids == ["abc12345", "xyz67890"]


def test_cache_list_reports_size(tmp_path: Path):
    cache_root = tmp_path / "yt-cache"
    (cache_root / "abc12345").mkdir(parents=True)
    (cache_root / "abc12345" / "f.bin").write_bytes(b"x" * 1024)
    entries = cache_list(cache_root)
    assert len(entries) == 1
    assert entries[0].size_bytes >= 1024


def test_cache_prune_nothing_when_young(tmp_path: Path):
    cache_root = tmp_path / "yt-cache"
    _touch(cache_root / "fresh" / "source.mp4", mtime_offset_days=1)
    pruned = cache_prune(cache_root, older_than_days=7)
    assert pruned == []
    assert (cache_root / "fresh").exists()


def test_cache_prune_removes_old_dirs(tmp_path: Path):
    cache_root = tmp_path / "yt-cache"
    _touch(cache_root / "old" / "source.mp4", mtime_offset_days=14)
    _touch(cache_root / "fresh" / "source.mp4", mtime_offset_days=1)
    pruned = cache_prune(cache_root, older_than_days=7)
    assert [p.name for p in pruned] == ["old"]
    assert not (cache_root / "old").exists()
    assert (cache_root / "fresh").exists()


def test_cache_prune_missing_root_is_noop(tmp_path: Path):
    pruned = cache_prune(tmp_path / "no-such-dir", older_than_days=7)
    assert pruned == []
