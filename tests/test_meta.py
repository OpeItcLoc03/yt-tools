"""Tests for yt-meta — full-metadata fetch + markdown render.

Two layers: ``fetch_full_metadata`` (subprocess/yt-dlp mocked) and the pure
``metadata_to_markdown`` render (driven by dicts, with/without heatmap and
chapters to exercise the graceful-absence branches). Plus a CLI guard mirroring
the abort-cleanliness contract in test_failure_modes.py.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from yt_tools import meta as meta_mod
from yt_tools._metadata import MetadataError, fetch_full_metadata
from yt_tools.meta import metadata_to_markdown

_VID = "abcDEF12345"
_URL = f"https://youtu.be/{_VID}"

_FULL_INFO = {
    "title": "How transformers work",
    "description": "A deep dive into attention.\nSecond paragraph.",
    "webpage_url": _URL,
    "uploader": "3Blue1Brown",
    "channel": "3Blue1Brown",
    "channel_follower_count": 6000000,
    "duration": 1200,
    "view_count": 1234567,
    "like_count": 89000,
    "comment_count": 4200,
    "upload_date": "20240115",
    "categories": ["Education"],
    "tags": ["math", "transformers", "attention"],
    "chapters": [
        {"start_time": 0.0, "end_time": 154.0, "title": "Intro"},
        {"start_time": 154.0, "end_time": 600.0, "title": "Attention"},
    ],
    "heatmap": [
        {"start_time": 0.0, "end_time": 10.0, "value": 0.2},
        {"start_time": 83.0, "end_time": 90.0, "value": 0.95},
        {"start_time": 296.0, "end_time": 305.0, "value": 0.71},
    ],
    "subtitles": {"en": [{}], "ru": [{}]},
    "automatic_captions": {"en": [{}], "es": [{}]},
}

_MINIMAL_INFO = {
    "title": "Bare clip",
    "webpage_url": _URL,
    "duration": 42,
    # no description, chapters, heatmap, counts, tags, subtitles
}


# --- fetch_full_metadata (subprocess mocked) ---------------------------------


def test_fetch_full_metadata_returns_full_dict():
    proc = type("P", (), {"returncode": 0, "stdout": json.dumps(_FULL_INFO), "stderr": ""})()
    with patch("yt_tools._metadata.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools._metadata.subprocess.run", return_value=proc):
        info = fetch_full_metadata(_URL)
    # Full dict — not the 4-key slim shape.
    assert info["title"] == "How transformers work"
    assert info["heatmap"][1]["value"] == 0.95
    assert info["chapters"][0]["title"] == "Intro"


def test_fetch_full_metadata_raises_when_yt_dlp_missing():
    with patch("yt_tools._metadata.shutil.which", return_value=None):
        with pytest.raises(MetadataError):
            fetch_full_metadata(_URL)


def test_slim_fetch_unchanged_additive_invariant():
    """The slim fetch_video_metadata (transcript.py consumer) still returns 4 keys."""
    from yt_tools._metadata import fetch_video_metadata

    proc = type("P", (), {"returncode": 0, "stdout": json.dumps(_FULL_INFO), "stderr": ""})()
    with patch("yt_tools._metadata.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools._metadata.subprocess.run", return_value=proc):
        slim = fetch_video_metadata(_URL)
    assert set(slim) == {"title", "channel", "duration", "url"}


# --- metadata_to_markdown (pure render) --------------------------------------


def test_render_full_includes_all_sections():
    md = metadata_to_markdown(_FULL_INFO)
    assert "# How transformers work" in md
    assert "A deep dive into attention." in md
    # chapters as [mm:ss] title
    assert "[0:00] Intro" in md
    assert "[2:34] Attention" in md
    # heatmap most-replayed: highest-value segment first, [mm:ss]–[mm:ss]
    assert "[1:23]" in md and "[1:30]" in md
    # counts (comma-grouped)
    assert "1,234,567" in md
    assert "2024-01-15" in md  # upload_date reformatted
    # taxonomy
    assert "transformers" in md
    assert "Education" in md
    assert "3Blue1Brown" in md
    # subtitle languages (union of subtitles + automatic_captions)
    assert "en" in md and "ru" in md and "es" in md


def test_render_most_replayed_ranked_by_value():
    md = metadata_to_markdown(_FULL_INFO)
    # 0.95 segment (1:23) must appear before the 0.71 segment (4:56) in the
    # most-replayed list.
    assert md.index("[1:23]") < md.index("[4:56]")


def test_render_minimal_is_graceful():
    """No heatmap / chapters / counts → render must not raise and must omit those sections."""
    md = metadata_to_markdown(_MINIMAL_INFO)
    assert "# Bare clip" in md
    assert "Most replayed" not in md
    assert "Chapters" not in md


def test_render_no_heatmap_keeps_chapters():
    info = dict(_FULL_INFO)
    info.pop("heatmap")
    md = metadata_to_markdown(info)
    assert "Chapters" in md
    assert "Most replayed" not in md


# --- CLI abort-cleanliness ---------------------------------------------------


def test_yt_meta_no_empty_cache_dir_on_fetch_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(meta_mod, "fetch_full_metadata", side_effect=MetadataError("boom")):
        rc = meta_mod.main([_URL])
    assert rc == 1
    assert not (tmp_path / "yt-cache" / _VID).exists()


def test_yt_meta_success_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(meta_mod, "fetch_full_metadata", return_value=_FULL_INFO):
        rc = meta_mod.main([_URL])
    assert rc == 0
    assert (tmp_path / "yt-cache" / _VID / "meta.md").exists()
