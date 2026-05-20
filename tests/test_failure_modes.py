"""Abort-cleanliness contract: a failed CLI run leaves no empty cache dirs behind.

The SKILL.md Failure-modes table promises "никогда не оставляй наполовину готовое
состояние". These tests guard against regressions where mkdir runs before the
fragile fetch step and leaves an empty ``yt-cache/<vid>/`` on FS after abort.
"""

from __future__ import annotations

from unittest.mock import patch

from yt_tools import transcript as transcript_mod
from yt_tools import watch as watch_mod
from yt_tools.markdown import Snippet

_VID = "abcDEF12345"
_URL = f"https://youtu.be/{_VID}"
_FAKE_META = {"title": "T", "channel": "", "duration": 10, "url": _URL}


def test_yt_transcript_no_empty_cache_dir_on_fetch_failure(tmp_path, monkeypatch):
    """yt-transcript must not leave yt-cache/<vid>/ on disk after a fetch error."""
    monkeypatch.chdir(tmp_path)
    with patch.object(transcript_mod, "fetch_video_metadata", return_value=_FAKE_META), \
         patch.object(transcript_mod, "_fetch_snippets", side_effect=RuntimeError("Subtitles disabled")):
        rc = transcript_mod.main([_URL])
    assert rc == 1
    assert not (tmp_path / "yt-cache" / _VID).exists(), "empty cache dir left behind"


def test_yt_transcript_succeeds_creates_dir(tmp_path, monkeypatch):
    """Happy-path sanity: dir IS created when fetch succeeds."""
    monkeypatch.chdir(tmp_path)
    fake_snippets = ([Snippet("hi", 0.0, 1.0)], "en")
    with patch.object(transcript_mod, "fetch_video_metadata", return_value=_FAKE_META), \
         patch.object(transcript_mod, "_fetch_snippets", return_value=fake_snippets):
        rc = transcript_mod.main([_URL])
    assert rc == 0
    assert (tmp_path / "yt-cache" / _VID / "transcript.md").exists()


def test_yt_watch_no_empty_cache_dir_on_snippets_failure(tmp_path, monkeypatch):
    """yt-watch must not leave yt-cache/<vid>/ if _fetch_snippets fails before _ensure_source_mp4."""
    monkeypatch.chdir(tmp_path)
    with patch.object(watch_mod, "fetch_video_metadata", return_value=_FAKE_META), \
         patch.object(watch_mod, "_fetch_snippets", side_effect=RuntimeError("Subtitles disabled")):
        rc = watch_mod.main([_URL])
    assert rc == 1
    assert not (tmp_path / "yt-cache" / _VID).exists(), "empty cache dir left behind"
