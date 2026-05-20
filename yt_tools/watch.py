"""yt-watch CLI — combined transcript + scene-frames in one markdown with sidecar embed.

Secondary use-case: a single ``watch.md`` per video that interleaves transcript paragraphs
with ``![](frames/frame_<mmss>.jpg)`` next to the matching scene boundary, so an agent can
``Read`` one document and "see" the video at the moments where it visually changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from yt_tools._metadata import MetadataError, fetch_video_metadata
from yt_tools.core import (
    cache_dir_for,
    extract_video_id,
    format_seconds_for_filename,
    format_seconds_to_mmss,
)
from yt_tools.frames import (
    DEFAULT_SCENE_THRESHOLD,
    _detect_scene_timestamps,
    _ensure_source_mp4,
    _ffmpeg_extract_from_file,
)
from yt_tools.markdown import (
    DEFAULT_PARAGRAPH_GAP_SECONDS,
    Snippet,
    _group_paragraphs,
)
from yt_tools.transcript import _fetch_snippets


def _render_interleaved(
    title: str,
    channel: str,
    duration: int,
    lang: str,
    url: str,
    snippets: list[Snippet],
    frame_timestamps: list[float],
    frames_subdir: str = "frames",
    paragraph_gap_seconds: float = DEFAULT_PARAGRAPH_GAP_SECONDS,
) -> str:
    paragraphs = _group_paragraphs(snippets, paragraph_gap_seconds)
    duration_str = format_seconds_to_mmss(float(duration)) if duration else "?"

    lines: list[str] = [f"# {title}", ""]
    meta_bits: list[str] = []
    if channel:
        meta_bits.append(f"**Channel:** {channel}")
    meta_bits.append(f"**Duration:** {duration_str}")
    if lang:
        meta_bits.append(f"**Lang:** {lang}")
    if url:
        meta_bits.append(f"**URL:** {url}")
    lines.append("  ".join(meta_bits))
    lines.append("")
    lines.append("---")
    lines.append("")

    def _emit_image(ts: float) -> None:
        anchor = format_seconds_for_filename(ts)
        label = format_seconds_to_mmss(ts)
        lines.append(f"![scene at {label}]({frames_subdir}/frame_{anchor}.jpg)")
        lines.append("")

    frame_iter = iter(sorted(frame_timestamps))
    next_frame: float | None = next(frame_iter, None)
    para_starts = [p[0] for p in paragraphs]

    for i, (start, text) in enumerate(paragraphs):
        next_para_start = para_starts[i + 1] if i + 1 < len(paragraphs) else float("inf")
        # Frames before this paragraph (only possible for i == 0).
        while next_frame is not None and next_frame < start:
            _emit_image(next_frame)
            next_frame = next(frame_iter, None)
        lines.append(f"[{format_seconds_to_mmss(start)}] {text}")
        lines.append("")
        # Frames that fall inside this paragraph (between its start and the next paragraph).
        while next_frame is not None and next_frame < next_para_start:
            _emit_image(next_frame)
            next_frame = next(frame_iter, None)

    # Any trailing frames after the last paragraph (no transcript exists for them).
    while next_frame is not None:
        _emit_image(next_frame)
        next_frame = next(frame_iter, None)

    return "\n".join(lines).rstrip() + "\n"


def run(
    url: str,
    out_dir: Path | None = None,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    languages: list[str] | None = None,
) -> Path:
    languages = languages or ["en"]
    video_id = extract_video_id(url)
    if out_dir is None:
        out_dir = cache_dir_for(url)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        meta = fetch_video_metadata(url)
    except MetadataError as e:
        print(f"warning: {e} — using minimal metadata", file=sys.stderr)
        meta = {"title": video_id, "channel": "", "duration": 0, "url": url}

    snippets, lang = _fetch_snippets(video_id, languages)

    source = _ensure_source_mp4(url, out_dir / "source.mp4")
    scene_timestamps = _detect_scene_timestamps(source, scene_threshold)

    for s in scene_timestamps:
        out_path = frames_dir / f"frame_{format_seconds_for_filename(s)}.jpg"
        if not out_path.exists():
            _ffmpeg_extract_from_file(source, s, out_path)

    md = _render_interleaved(
        title=meta["title"],
        channel=meta["channel"],
        duration=meta["duration"],
        lang=lang,
        url=meta["url"],
        snippets=snippets,
        frame_timestamps=scene_timestamps,
    )
    watch_md = out_dir / "watch.md"
    watch_md.write_text(md, encoding="utf-8")
    return watch_md.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yt-watch",
        description="Combined transcript + scene-frames in one markdown (sidecar embed).",
    )
    parser.add_argument("url", help="YouTube URL or bare video id")
    parser.add_argument("--out", type=Path, default=None, help="Output dir (default: ./yt-cache/<vid>/)")
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_THRESHOLD,
        help=f"PySceneDetect ContentDetector threshold (default {DEFAULT_SCENE_THRESHOLD}).",
    )
    parser.add_argument("--lang", default="en", help="Comma-separated language preference (default: en).")
    args = parser.parse_args(argv)

    languages = [lang.strip() for lang in args.lang.split(",") if lang.strip()]
    try:
        path = run(args.url, out_dir=args.out, scene_threshold=args.scene_threshold, languages=languages)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
