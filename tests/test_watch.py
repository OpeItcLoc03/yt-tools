"""Tests for the yt-watch interleaving renderer."""

from yt_tools.markdown import Snippet
from yt_tools.watch import _render_interleaved


def _s(text: str, start: float, duration: float = 2.0) -> Snippet:
    return Snippet(text=text, start=start, duration=duration)


META = dict(title="T", channel="C", duration=600, lang="en", url="https://youtu.be/x")


def test_frame_inside_paragraph_appears_after():
    md = _render_interleaved(
        snippets=[_s("para one body", 0.0), _s("para two body", 60.0)],
        frame_timestamps=[10.0],
        **META,
    )
    p1 = md.index("para one body")
    img = md.index("frame_0010")
    p2 = md.index("para two body")
    assert p1 < img < p2


def test_multiple_frames_in_one_paragraph():
    md = _render_interleaved(
        snippets=[_s("only paragraph here", 0.0)],
        frame_timestamps=[5.0, 10.0, 20.0],
        **META,
    )
    assert md.count("![scene at") == 3
    body = md.index("only paragraph here")
    assert all(md.index(f"frame_{ts}") > body for ts in ("0005", "0010", "0020"))


def test_leading_frame_before_first_paragraph_emits_first():
    md = _render_interleaved(
        snippets=[_s("first", 30.0)],
        frame_timestamps=[5.0],
        **META,
    )
    img = md.index("frame_0005")
    body = md.index("first")
    assert img < body


def test_trailing_frames_after_last_paragraph():
    md = _render_interleaved(
        snippets=[_s("first", 0.0)],
        frame_timestamps=[120.0],
        **META,
    )
    body = md.index("first")
    img = md.index("frame_0200")
    assert body < img


def test_no_frames_produces_plain_paragraphs():
    md = _render_interleaved(
        snippets=[_s("solo", 0.0)],
        frame_timestamps=[],
        **META,
    )
    assert "![scene" not in md
    assert "solo" in md


def test_header_metadata_present():
    md = _render_interleaved(
        snippets=[_s("body", 0.0)],
        frame_timestamps=[],
        **META,
    )
    assert "# T" in md
    assert "Channel:" in md
    assert "Duration:" in md
    assert "Lang:" in md
