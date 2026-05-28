"""yt-meta CLI — render a YouTube video's full metadata as markdown.

Tier 1, zero added cost: reuses the same ``yt-dlp --dump-json`` the engine already
calls (via :func:`yt_tools._metadata.fetch_full_metadata`) and renders the fields
the slim transcript path throws away — description, chapters, most-replayed
heatmap, view/like/comment counts, tags, uploader, subtitle languages.

Render style mirrors ``markdown.py``: ``# title`` header, ``[mm:ss]`` anchors on
chapters (copy-pasteable into ``yt-frames --timestamps``), every field via
``.get(...)`` so missing sections degrade gracefully instead of raising.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yt_tools._metadata import MetadataError, fetch_full_metadata
from yt_tools.core import (
    cache_dir_for,
    force_utf8_streams,
    format_count,
    format_seconds_to_mmss,
    format_upload_date_iso,
)

# How many heatmap segments to surface in the "Most replayed" section.
_MOST_REPLAYED_LIMIT = 5


def _chapters_section(chapters: list[dict]) -> list[str]:
    lines = ["## Chapters", ""]
    for ch in chapters:
        anchor = format_seconds_to_mmss(float(ch.get("start_time") or 0))
        title = (ch.get("title") or "").strip() or "(untitled)"
        lines.append(f"[{anchor}] {title}")
    lines.append("")
    return lines


def _most_replayed_section(heatmap: list[dict]) -> list[str]:
    # Rank segments by replay value; surface the hottest few as [mm:ss]–[mm:ss].
    ranked = sorted(heatmap, key=lambda seg: seg.get("value") or 0.0, reverse=True)
    top = ranked[:_MOST_REPLAYED_LIMIT]
    if not top:
        return []
    lines = ["## Most replayed", ""]
    for seg in top:
        start = format_seconds_to_mmss(float(seg.get("start_time") or 0))
        end = format_seconds_to_mmss(float(seg.get("end_time") or 0))
        lines.append(f"[{start}]–[{end}]")
    lines.append("")
    return lines


def _subtitle_languages(info: dict) -> list[str]:
    langs = set(info.get("subtitles") or {})
    langs |= set(info.get("automatic_captions") or {})
    # Drop the "live_chat" pseudo-track yt-dlp sometimes lists.
    langs.discard("live_chat")
    return sorted(langs)


def metadata_to_markdown(info: dict) -> str:
    """Render a yt-dlp info-dict as markdown. Every section is optional and omitted
    when its source field is absent — never raises on a sparse dict."""
    title = info.get("title") or "Untitled"
    url = info.get("webpage_url") or info.get("original_url") or ""
    uploader = info.get("uploader") or info.get("channel") or ""
    duration = info.get("duration") or 0

    lines: list[str] = [f"# {title}", ""]

    meta_bits: list[str] = []
    if uploader:
        meta_bits.append(f"**Channel:** {uploader}")
    if duration:
        meta_bits.append(f"**Duration:** {format_seconds_to_mmss(float(duration))}")
    if url:
        meta_bits.append(f"**URL:** {url}")
    if meta_bits:
        lines.append("  ".join(meta_bits))
        lines.append("")
    lines.append("---")
    lines.append("")

    description = (info.get("description") or "").strip()
    if description:
        lines += ["## Description", "", description, ""]

    chapters = info.get("chapters")
    if chapters:
        lines += _chapters_section(chapters)

    heatmap = info.get("heatmap")
    if heatmap:
        lines += _most_replayed_section(heatmap)

    # Stats — only emit rows whose count is present and numeric.
    stat_rows: list[str] = []
    for label, key in (
        ("Views", "view_count"),
        ("Likes", "like_count"),
        ("Comments", "comment_count"),
        ("Subscribers", "channel_follower_count"),
    ):
        formatted = format_count(info.get(key))
        if formatted is not None:
            stat_rows.append(f"- {label}: {formatted}")
    upload = format_upload_date_iso(info.get("upload_date"))
    if upload:
        stat_rows.append(f"- Uploaded: {upload}")
    if stat_rows:
        lines += ["## Stats", "", *stat_rows, ""]

    categories = info.get("categories")
    if categories:
        lines += ["## Categories", "", ", ".join(categories), ""]

    tags = info.get("tags")
    if tags:
        lines += ["## Tags", "", ", ".join(tags), ""]

    langs = _subtitle_languages(info)
    if langs:
        lines += ["## Subtitle languages", "", ", ".join(langs), ""]

    return "\n".join(lines).rstrip() + "\n"


def run(url: str, out: Path | None = None) -> Path:
    """Fetch full metadata and write ``meta.md``. Returns the artifact path."""
    if out is None:
        out = cache_dir_for(url) / "meta.md"

    info = fetch_full_metadata(url)
    md = metadata_to_markdown(info)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out.resolve()


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="yt-meta",
        description="Render a YouTube video's full metadata (description, chapters, "
        "most-replayed, counts, tags) as markdown.",
    )
    parser.add_argument("url", help="YouTube URL or bare video id")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: ./yt-cache/<vid>/meta.md)",
    )
    args = parser.parse_args(argv)

    try:
        path = run(args.url, out=args.out)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
