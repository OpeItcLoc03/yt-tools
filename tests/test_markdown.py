"""Tests for snippets→markdown rendering."""

from yt_tools.markdown import Snippet, snippets_to_markdown


def _s(text: str, start: float, duration: float = 2.0) -> Snippet:
    return Snippet(text=text, start=start, duration=duration)


def test_header_includes_metadata():
    md = snippets_to_markdown(
        snippets=[_s("Hello world", 0.0)],
        metadata={
            "title": "Test Title",
            "channel": "Test Channel",
            "duration": 120,
            "lang": "en",
            "url": "https://youtu.be/abc",
        },
    )
    assert "# Test Title" in md
    assert "Test Channel" in md
    assert "2:00" in md  # duration formatted
    assert "https://youtu.be/abc" in md
    assert "en" in md


def test_paragraph_anchors_use_mmss():
    md = snippets_to_markdown(
        snippets=[
            _s("First sentence.", 0.0),
            _s("Second sentence.", 83.0),
        ],
        metadata={
            "title": "T",
            "channel": "C",
            "duration": 100,
            "lang": "en",
            "url": "u",
        },
        paragraph_gap_seconds=5.0,
    )
    assert "[0:00]" in md
    assert "[1:23]" in md


def test_close_snippets_merge_into_paragraph():
    snippets = [_s(f"chunk{i}", float(i)) for i in range(5)]
    md = snippets_to_markdown(
        snippets=snippets,
        metadata={"title": "T", "channel": "C", "duration": 10, "lang": "en", "url": "u"},
        paragraph_gap_seconds=5.0,
    )
    assert md.count("[0:00]") == 1
    assert "chunk0" in md and "chunk4" in md


def test_long_gap_splits_paragraph():
    snippets = [
        _s("first", 0.0),
        _s("second", 60.0),  # 60s gap > 5s default
    ]
    md = snippets_to_markdown(
        snippets=snippets,
        metadata={"title": "T", "channel": "C", "duration": 100, "lang": "en", "url": "u"},
        paragraph_gap_seconds=5.0,
    )
    assert "[0:00]" in md
    assert "[1:00]" in md


def test_xml_entities_decoded():
    md = snippets_to_markdown(
        snippets=[_s("it&#39;s &amp; that", 0.0)],
        metadata={"title": "T", "channel": "C", "duration": 10, "lang": "en", "url": "u"},
    )
    assert "it's & that" in md
    assert "&#39;" not in md
    assert "&amp;" not in md


def test_anchor_format_is_copyable_to_timestamps_flag():
    md = snippets_to_markdown(
        snippets=[_s("a", 83.0), _s("b", 296.0)],
        metadata={"title": "T", "channel": "C", "duration": 400, "lang": "en", "url": "u"},
        paragraph_gap_seconds=5.0,
    )
    assert "[1:23]" in md
    assert "[4:56]" in md
