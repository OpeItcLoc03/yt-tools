"""yt-comments CLI — scrape a YouTube video's comments into markdown.

Tier 2 / **not free**: unlike ``yt-meta`` (which rides the existing
``--dump-json``), comments are a separate paginated scrape. On viral videos a
full pull is minutes of network traffic, so this CLI always caps the fetch — top
50 by default, raise with ``--max`` only when you actually need more. Call it
deliberately, never as part of a metadata flow.

Render style mirrors the other CLIs: ``# Comments — <title>`` header, top-level
comments in order, replies nested as blockquotes under their parent.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from yt_tools._metadata import MetadataError
from yt_tools.core import cache_dir_for, force_utf8_streams

DEFAULT_MAX_COMMENTS = 50


def build_yt_dlp_cmd(
    url: str,
    max_comments: int = DEFAULT_MAX_COMMENTS,
    sort: str = "top",
    yt_dlp_bin: str = "yt-dlp",
) -> list[str]:
    """Build the ``yt-dlp`` argv that dumps the info-dict *with* comments.

    ``--write-comments`` enables comment extraction; ``--extractor-args`` caps the
    pull and sets sort order so we never paginate the whole thread by accident.
    """
    return [
        yt_dlp_bin,
        "--dump-json",
        "--skip-download",
        "--no-warnings",
        "--write-comments",
        "--extractor-args",
        f"youtube:max_comments={max_comments},comment_sort={sort}",
        url,
    ]


def fetch_comments(
    url: str,
    max_comments: int = DEFAULT_MAX_COMMENTS,
    sort: str = "top",
    yt_dlp_bin: str = "yt-dlp",
) -> dict:
    """Return the yt-dlp info-dict (including a ``comments`` list) for the URL.

    Raises MetadataError if yt-dlp is missing, returns non-zero, or emits non-JSON.
    """
    if not shutil.which(yt_dlp_bin):
        raise MetadataError(f"yt-dlp not found on PATH (looked for {yt_dlp_bin!r})")
    cmd = build_yt_dlp_cmd(url, max_comments=max_comments, sort=sort, yt_dlp_bin=yt_dlp_bin)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as e:
        raise MetadataError(f"yt-dlp comment scrape timed out for {url}") from e
    if proc.returncode != 0:
        raise MetadataError(f"yt-dlp --write-comments failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MetadataError(f"yt-dlp returned non-JSON output: {e}") from e


def _format_comment(c: dict) -> list[str]:
    """Render one comment's byline + body lines (no indentation applied yet)."""
    author = c.get("author") or "(unknown)"
    if c.get("author_is_uploader"):
        author = f"{author} (creator)"
    bits = [f"**{author}**"]
    likes = c.get("like_count")
    if likes:
        bits.append(f"{int(likes):,} likes")
    when = c.get("_time_text") or c.get("time_text")
    if when:
        bits.append(str(when))
    byline = " · ".join(bits)
    body = (c.get("text") or "").strip()
    lines = [byline]
    if body:
        lines.append("")
        lines.extend(body.splitlines())
    return lines


def comments_to_markdown(info: dict) -> str:
    """Render the comments payload as markdown. Graceful on empty/missing lists."""
    title = info.get("title") or "Untitled"
    url = info.get("webpage_url") or info.get("original_url") or ""
    comments = info.get("comments") or []

    # Split into top-level and replies-by-parent, preserving yt-dlp's (sorted) order.
    top_level: list[dict] = []
    replies: dict[str, list[dict]] = {}
    for c in comments:
        parent = c.get("parent")
        if not parent or parent == "root":
            top_level.append(c)
        else:
            replies.setdefault(parent, []).append(c)

    lines: list[str] = [f"# Comments — {title}", ""]
    meta_bits = [f"**Fetched:** {len(comments)}"]
    if info.get("comment_count") is not None:
        meta_bits.append(f"**Total on video:** {int(info['comment_count']):,}")
    if url:
        meta_bits.append(f"**URL:** {url}")
    lines.append("  ".join(meta_bits))
    lines += ["", "---", ""]

    if not comments:
        lines.append("_No comments._")
        return "\n".join(lines).rstrip() + "\n"

    for c in top_level:
        lines.extend(_format_comment(c))
        lines.append("")
        for reply in replies.get(c.get("id", ""), []):
            # Nest replies as a blockquote under their parent.
            for rline in _format_comment(reply):
                lines.append(f"> {rline}" if rline else ">")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run(
    url: str,
    out: Path | None = None,
    max_comments: int = DEFAULT_MAX_COMMENTS,
    sort: str = "top",
) -> Path:
    """Fetch comments and write ``comments.md``. Returns the artifact path."""
    if out is None:
        out = cache_dir_for(url) / "comments.md"

    info = fetch_comments(url, max_comments=max_comments, sort=sort)
    md = comments_to_markdown(info)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out.resolve()


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="yt-comments",
        description="Scrape a YouTube video's comments into markdown. Separate paginated "
        "fetch — can take minutes on viral videos; capped at top 50 by default.",
    )
    parser.add_argument("url", help="YouTube URL or bare video id")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: ./yt-cache/<vid>/comments.md)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_COMMENTS,
        dest="max_comments",
        help=f"Max comments to fetch (default: {DEFAULT_MAX_COMMENTS}). Higher = slower.",
    )
    parser.add_argument(
        "--sort",
        choices=["top", "new"],
        default="top",
        help="Comment sort order (default: top).",
    )
    args = parser.parse_args(argv)

    try:
        path = run(args.url, out=args.out, max_comments=args.max_comments, sort=args.sort)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
