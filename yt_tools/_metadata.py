"""Fetch video metadata via ``yt-dlp --dump-json --skip-download``."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class MetadataError(RuntimeError):
    pass


def fetch_video_metadata(url: str, yt_dlp_bin: str = "yt-dlp") -> dict[str, Any]:
    """Return ``{"title", "channel", "duration", "url"}`` for the given URL.

    Calls ``yt-dlp --dump-json --skip-download <url>``. Raises MetadataError if yt-dlp
    is not on PATH or returns non-zero.
    """
    if not shutil.which(yt_dlp_bin):
        raise MetadataError(f"yt-dlp not found on PATH (looked for {yt_dlp_bin!r})")
    try:
        proc = subprocess.run(
            [yt_dlp_bin, "--dump-json", "--skip-download", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MetadataError(f"yt-dlp --dump-json timed out for {url}") from e
    if proc.returncode != 0:
        raise MetadataError(f"yt-dlp --dump-json failed: {proc.stderr.strip()}")
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MetadataError(f"yt-dlp returned non-JSON output: {e}") from e
    return {
        "title": info.get("title", "Untitled"),
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": int(info.get("duration") or 0),
        "url": info.get("webpage_url") or url,
    }
