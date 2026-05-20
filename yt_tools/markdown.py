"""Transcript snippet grouping → clean markdown with [mm:ss] anchors."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable, Sequence

from yt_tools.core import format_seconds_to_mmss

DEFAULT_PARAGRAPH_GAP_SECONDS = 4.0


@dataclass(frozen=True)
class Snippet:
    """A timestamped transcript fragment. Mirrors youtube_transcript_api.FetchedTranscriptSnippet shape."""

    text: str
    start: float
    duration: float = 0.0


def _clean(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\n", " ").strip()
    return " ".join(text.split())


def _group_paragraphs(
    snippets: Sequence[Snippet], paragraph_gap_seconds: float
) -> list[tuple[float, str]]:
    paragraphs: list[tuple[float, str]] = []
    cur_start: float | None = None
    cur_parts: list[str] = []
    last_end = 0.0
    for s in snippets:
        clean = _clean(s.text)
        if not clean:
            continue
        if cur_start is None:
            cur_start = s.start
            cur_parts = [clean]
            last_end = s.start + s.duration
            continue
        if s.start - last_end > paragraph_gap_seconds:
            paragraphs.append((cur_start, " ".join(cur_parts)))
            cur_start = s.start
            cur_parts = [clean]
        else:
            cur_parts.append(clean)
        last_end = s.start + s.duration
    if cur_start is not None:
        paragraphs.append((cur_start, " ".join(cur_parts)))
    return paragraphs


def snippets_to_markdown(
    snippets: Iterable[Snippet],
    metadata: dict,
    paragraph_gap_seconds: float = DEFAULT_PARAGRAPH_GAP_SECONDS,
) -> str:
    """Render snippets as clean markdown with metadata header and [mm:ss] paragraph anchors.

    The anchors use the same format that ``yt-frames --timestamps`` accepts, so the agent
    can copy-paste directly.

    Required ``metadata`` keys: ``title``, ``channel``, ``duration``, ``lang``, ``url``.
    """
    title = metadata.get("title", "Untitled")
    channel = metadata.get("channel", "")
    duration = metadata.get("duration", 0)
    lang = metadata.get("lang", "")
    url = metadata.get("url", "")

    duration_str = format_seconds_to_mmss(float(duration)) if duration else "?"

    header_lines = [f"# {title}", ""]
    meta_bits = []
    if channel:
        meta_bits.append(f"**Channel:** {channel}")
    meta_bits.append(f"**Duration:** {duration_str}")
    if lang:
        meta_bits.append(f"**Lang:** {lang}")
    if url:
        meta_bits.append(f"**URL:** {url}")
    header_lines.append("  ".join(meta_bits))
    header_lines.append("")
    header_lines.append("---")
    header_lines.append("")

    body_lines: list[str] = []
    paragraphs = _group_paragraphs(list(snippets), paragraph_gap_seconds)
    for start, text in paragraphs:
        anchor = format_seconds_to_mmss(start)
        body_lines.append(f"[{anchor}] {text}")
        body_lines.append("")

    return "\n".join(header_lines + body_lines).rstrip() + "\n"
