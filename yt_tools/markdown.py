"""Transcript snippet grouping → clean markdown with [mm:ss] anchors."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable, Sequence

from yt_tools.core import format_seconds_to_mmss

DEFAULT_PARAGRAPH_GAP_SECONDS = 4.0
# Hard cap on a paragraph's elapsed-time span — guarantees anchors at sane intervals
# even when snippets stream without 4s gaps (community/auto-submitted subs).
DEFAULT_MAX_PARAGRAPH_SECONDS = 45.0
# Minimum elapsed time before a sentence-final punctuation mark is allowed to split.
DEFAULT_SENTENCE_SPLIT_SECONDS = 15.0

_SENTENCE_END_CHARS = frozenset(".?!…")


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


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip().rstrip(')"]\'')
    return bool(stripped) and stripped[-1] in _SENTENCE_END_CHARS


def _group_paragraphs(
    snippets: Sequence[Snippet],
    paragraph_gap_seconds: float,
    max_paragraph_seconds: float = DEFAULT_MAX_PARAGRAPH_SECONDS,
    sentence_split_seconds: float = DEFAULT_SENTENCE_SPLIT_SECONDS,
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
        gap = s.start - last_end
        elapsed = s.start - cur_start
        split = (
            gap > paragraph_gap_seconds
            or elapsed > max_paragraph_seconds
            or (elapsed >= sentence_split_seconds and _ends_sentence(cur_parts[-1]))
        )
        if split:
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
    max_paragraph_seconds: float = DEFAULT_MAX_PARAGRAPH_SECONDS,
    sentence_split_seconds: float = DEFAULT_SENTENCE_SPLIT_SECONDS,
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
    paragraphs = _group_paragraphs(
        list(snippets),
        paragraph_gap_seconds,
        max_paragraph_seconds,
        sentence_split_seconds,
    )
    for start, text in paragraphs:
        anchor = format_seconds_to_mmss(start)
        body_lines.append(f"[{anchor}] {text}")
        body_lines.append("")

    return "\n".join(header_lines + body_lines).rstrip() + "\n"
