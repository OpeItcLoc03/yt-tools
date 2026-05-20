"""``yt-tools`` umbrella CLI — currently exposes ``cache list`` / ``cache prune``."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from yt_tools.cache import cache_list, cache_prune, format_size

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(d|day|days|h|hour|hours)?$", re.IGNORECASE)


def parse_age(spec: str) -> float:
    """Parse ``7d`` / ``12h`` / bare days. Returns days as float."""
    m = _DURATION_RE.match(spec.strip())
    if not m:
        raise ValueError(f"invalid duration: {spec!r}")
    value = float(m.group(1))
    unit = (m.group(2) or "d").lower()
    if unit in ("d", "day", "days"):
        return value
    if unit in ("h", "hour", "hours"):
        return value / 24.0
    raise ValueError(f"invalid duration unit: {unit!r}")


def _cache_root(base: Path | None) -> Path:
    return (base or Path.cwd()) / "yt-cache"


def cmd_cache_list(args: argparse.Namespace) -> int:
    root = _cache_root(args.base)
    entries = cache_list(root)
    if not entries:
        print(f"(empty: {root})")
        return 0
    now = time.time()
    total = 0
    for e in entries:
        age_days = (now - e.mtime) / 86400
        print(f"{e.video_id}  {format_size(e.size_bytes):>10}  {age_days:5.1f}d  {e.path}")
        total += e.size_bytes
    print(f"\ntotal: {len(entries)} videos, {format_size(total)}")
    return 0


def cmd_cache_prune(args: argparse.Namespace) -> int:
    root = _cache_root(args.base)
    try:
        days = parse_age(args.older_than)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    removed = cache_prune(root, older_than_days=days)
    if not removed:
        print(f"(nothing to prune in {root})")
        return 0
    for p in removed:
        print(f"removed: {p}")
    print(f"\npruned {len(removed)} dirs older than {days}d")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yt-tools", description="yt-tools umbrella CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cache = sub.add_parser("cache", help="Manage source-mp4 cache")
    cache_sub = cache.add_subparsers(dest="cache_cmd", required=True)

    cache_list_p = cache_sub.add_parser("list", help="List cached videos")
    cache_list_p.add_argument("--base", type=Path, default=None, help="Base dir containing yt-cache/ (default: cwd)")
    cache_list_p.set_defaults(func=cmd_cache_list)

    cache_prune_p = cache_sub.add_parser("prune", help="Remove old cached videos")
    cache_prune_p.add_argument("--older-than", default="7d", help="Age threshold, e.g. 7d / 12h (default: 7d)")
    cache_prune_p.add_argument("--base", type=Path, default=None, help="Base dir containing yt-cache/ (default: cwd)")
    cache_prune_p.set_defaults(func=cmd_cache_prune)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
