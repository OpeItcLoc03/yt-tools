"""Tests for yt-comments — comment scrape + markdown render.

Layers: ``build_yt_dlp_cmd`` (pure — proves --max / sort map into extractor-args),
``comments_to_markdown`` (pure render of a mocked comments payload, top-level +
nested replies), and CLI wiring (subprocess/fetch mocked, abort-cleanliness).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from yt_tools import comments as comments_mod
from yt_tools._metadata import MetadataError
from yt_tools.comments import build_yt_dlp_cmd, comments_to_markdown, fetch_comments

_VID = "abcDEF12345"
_URL = f"https://youtu.be/{_VID}"

_PAYLOAD = {
    "title": "How transformers work",
    "webpage_url": _URL,
    "comment_count": 4200,
    "comments": [
        {
            "id": "top1",
            "parent": "root",
            "author": "@alice",
            "like_count": 1234,
            "_time_text": "2 weeks ago",
            "text": "First!\nMultiline body.",
            "author_is_uploader": False,
        },
        {
            "id": "top1.reply1",
            "parent": "top1",
            "author": "@creator",
            "like_count": 5,
            "_time_text": "1 week ago",
            "text": "thanks!",
            "author_is_uploader": True,
        },
        {
            "id": "top2",
            "parent": "root",
            "author": "@bob",
            "like_count": 0,
            "_time_text": "3 days ago",
            "text": "great vid",
            "author_is_uploader": False,
        },
    ],
}


# --- build_yt_dlp_cmd (pure) -------------------------------------------------


def test_build_cmd_default_top_50():
    cmd = build_yt_dlp_cmd(_URL, max_comments=50, sort="top", yt_dlp_bin="yt-dlp")
    joined = " ".join(cmd)
    assert "--write-comments" in cmd
    assert "max_comments=50" in joined
    assert "comment_sort=top" in joined
    assert _URL in cmd


def test_build_cmd_respects_max_flag():
    cmd = build_yt_dlp_cmd(_URL, max_comments=10, sort="top", yt_dlp_bin="yt-dlp")
    assert "max_comments=10" in " ".join(cmd)
    assert "max_comments=50" not in " ".join(cmd)


# --- fetch_comments (subprocess mocked) --------------------------------------


def test_fetch_comments_returns_payload():
    proc = type("P", (), {"returncode": 0, "stdout": json.dumps(_PAYLOAD), "stderr": ""})()
    with patch("yt_tools.comments.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools.comments.subprocess.run", return_value=proc) as run:
        info = fetch_comments(_URL, max_comments=10)
    assert len(info["comments"]) == 3
    # --max actually threaded into the yt-dlp invocation
    assert "max_comments=10" in " ".join(run.call_args.args[0])


def test_fetch_comments_raises_when_yt_dlp_missing():
    with patch("yt_tools.comments.shutil.which", return_value=None):
        with pytest.raises(MetadataError):
            fetch_comments(_URL)


# --- comments_to_markdown (pure render) --------------------------------------


def test_render_top_level_and_replies():
    md = comments_to_markdown(_PAYLOAD)
    assert "# Comments — How transformers work" in md
    assert "@alice" in md
    assert "1,234" in md  # like count formatted
    assert "2 weeks ago" in md
    assert "First!" in md
    assert "@bob" in md
    # reply is nested (blockquote) and marks the uploader
    assert "> " in md
    assert "@creator" in md
    assert "creator" in md.lower()


def test_render_reply_after_its_parent():
    md = comments_to_markdown(_PAYLOAD)
    assert md.index("@alice") < md.index("@creator") < md.index("@bob")


def test_render_counts_shown_fetched():
    md = comments_to_markdown(_PAYLOAD)
    # 3 fetched comments (2 top-level + 1 reply) — pin the actual counter line
    assert "**Fetched:** 3" in md


def test_render_no_comments_is_graceful():
    md = comments_to_markdown({"title": "Quiet", "webpage_url": _URL, "comments": []})
    assert "# Comments — Quiet" in md
    assert "No comments" in md or "0" in md


def test_render_missing_comments_key_graceful():
    md = comments_to_markdown({"title": "Quiet", "webpage_url": _URL})
    assert "Quiet" in md  # does not raise


# --- CLI ---------------------------------------------------------------------


def test_yt_comments_no_empty_cache_dir_on_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(comments_mod, "fetch_comments", side_effect=MetadataError("boom")):
        rc = comments_mod.main([_URL])
    assert rc == 1
    assert not (tmp_path / "yt-cache" / _VID).exists()


def test_yt_comments_success_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(comments_mod, "fetch_comments", return_value=_PAYLOAD) as f:
        rc = comments_mod.main([_URL, "--max", "25"])
    assert rc == 0
    assert (tmp_path / "yt-cache" / _VID / "comments.md").exists()
    # --max parsed and forwarded
    assert f.call_args.kwargs.get("max_comments") == 25 or 25 in f.call_args.args
