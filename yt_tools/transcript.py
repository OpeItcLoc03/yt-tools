"""yt-transcript CLI — fetch YouTube auto-subs and emit clean markdown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yt_tools._metadata import MetadataError, fetch_video_metadata
from yt_tools.core import cache_dir_for, extract_video_id, force_utf8_streams
from yt_tools.markdown import Snippet, snippets_to_markdown


def _fetch_snippets(video_id: str, languages: list[str]) -> tuple[list[Snippet], str]:
    """Fetch transcript snippets via youtube-transcript-api. Returns (snippets, lang)."""
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=languages)
    snippets = [Snippet(text=s.text, start=s.start, duration=s.duration) for s in fetched]
    lang = getattr(fetched, "language_code", languages[0] if languages else "")
    return snippets, lang


def run(
    url: str,
    out: Path | None = None,
    distill: bool = False,
    languages: list[str] | None = None,
) -> Path:
    """Fetch transcript and write to a markdown file. Returns the artifact path."""
    languages = languages or ["en"]
    video_id = extract_video_id(url)

    if out is None:
        out = cache_dir_for(url) / "transcript.md"

    try:
        meta = fetch_video_metadata(url)
    except MetadataError as e:
        print(f"warning: {e} — using minimal metadata", file=sys.stderr)
        meta = {"title": video_id, "channel": "", "duration": 0, "url": url}

    snippets, lang = _fetch_snippets(video_id, languages)
    meta["lang"] = lang

    md = snippets_to_markdown(snippets, meta)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    if distill:
        print(
            f"distill-hint: invoke mcp__interns__transcript_distill on {out.resolve()}",
            file=sys.stderr,
        )

    return out.resolve()


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="yt-transcript",
        description="Fetch YouTube transcript as clean markdown with [mm:ss] anchors.",
    )
    parser.add_argument("url", help="YouTube URL or bare video id")
    parser.add_argument("--out", type=Path, default=None, help="Output path (default: ./yt-cache/<vid>/transcript.md)")
    parser.add_argument(
        "--lang",
        default="en",
        help="Comma-separated language preference (default: en). Example: ru,en",
    )
    parser.add_argument(
        "--distill",
        action="store_true",
        help="Print a hint to invoke mcp__interns__transcript_distill on the artifact.",
    )
    args = parser.parse_args(argv)

    languages = [lang.strip() for lang in args.lang.split(",") if lang.strip()]
    try:
        path = run(args.url, out=args.out, distill=args.distill, languages=languages)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
