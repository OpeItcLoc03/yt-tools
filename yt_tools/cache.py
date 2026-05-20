"""Source-mp4 cache layout: ``<cwd>/yt-cache/<video-id>/...`` — list and prune helpers."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheEntry:
    video_id: str
    path: Path
    size_bytes: int
    mtime: float


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def cache_list(cache_root: Path) -> list[CacheEntry]:
    """List per-video subdirectories under ``cache_root``."""
    if not cache_root.exists():
        return []
    entries: list[CacheEntry] = []
    for child in sorted(cache_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        entries.append(
            CacheEntry(
                video_id=child.name,
                path=child,
                size_bytes=_dir_size(child),
                mtime=mtime,
            )
        )
    return entries


def cache_prune(cache_root: Path, older_than_days: float) -> list[Path]:
    """Remove cache subdirs whose mtime is older than ``older_than_days``.

    Returns the list of removed paths.
    """
    if not cache_root.exists():
        return []
    cutoff = time.time() - older_than_days * 86400
    removed: list[Path] = []
    for entry in cache_list(cache_root):
        if entry.mtime < cutoff:
            shutil.rmtree(entry.path, ignore_errors=True)
            removed.append(entry.path)
    return removed


def format_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"
