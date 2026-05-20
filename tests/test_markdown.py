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


def test_dense_snippets_split_by_max_duration_cap():
    # Regression: pre-fix, community-submitted EN-subs (e.g. 3blue1brown fNk_zzaMoSs)
    # collapsed into a single paragraph because snippet gaps stayed under 4s.
    # 200 snippets covering 100s with no gap and no sentence-end punctuation must
    # still split — at minimum once — via the max_paragraph_seconds cap.
    snippets = [_s(f"word{i}", i * 0.5, duration=0.5) for i in range(200)]
    md = snippets_to_markdown(
        snippets=snippets,
        metadata={"title": "T", "channel": "C", "duration": 100, "lang": "en", "url": "u"},
    )
    anchor_count = md.count("[0:") + md.count("[1:")
    assert anchor_count >= 3, f"expected >=3 anchors on 100s dense stream, got {anchor_count}; md=\n{md}"


def test_sentence_end_splits_after_min_interval():
    # Snippet 3 lands at t=16 (elapsed >= 15s default) and the previous text "third."
    # ends in sentence-final punctuation, so a new paragraph should start there.
    snippets = [
        _s("first.", 0.0, duration=2.0),
        _s("second.", 5.0, duration=2.0),
        _s("third.", 10.0, duration=2.0),
        _s("fourth.", 16.0, duration=2.0),
        _s("fifth.", 21.0, duration=2.0),
    ]
    md = snippets_to_markdown(
        snippets=snippets,
        metadata={"title": "T", "channel": "C", "duration": 30, "lang": "en", "url": "u"},
    )
    assert "[0:00]" in md
    assert "[0:16]" in md


def test_sentence_end_does_not_split_before_min_interval():
    # All sentence-ends but every snippet inside the 15s min-split window → one paragraph.
    snippets = [
        _s("first.", 0.0, duration=2.0),
        _s("second.", 3.0, duration=2.0),
        _s("third.", 6.0, duration=2.0),
        _s("fourth.", 9.0, duration=2.0),
    ]
    md = snippets_to_markdown(
        snippets=snippets,
        metadata={"title": "T", "channel": "C", "duration": 15, "lang": "en", "url": "u"},
    )
    # Only the leading [0:00] anchor.
    assert md.count("[0:00]") == 1
    assert "[0:03]" not in md and "[0:06]" not in md and "[0:09]" not in md
