"""Tests for yt-search — yt-dlp ytsearch + markdown render.

Layers: ``build_yt_dlp_cmd`` (pure — proves ``ytsearchN:`` query encoding and
flags), ``slugify`` (locale-free filename safety incl. unicode/Cyrillic edges),
``results_to_markdown`` (pure render of mocked yt-dlp JSON-lines, exercising
LIVE marker / missing duration / missing upload_date and the "url-as-last-field"
contract relied on by bulk-pipeline ``grep``), CLI smoke + abort-cleanliness.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from yt_tools import search as search_mod
from yt_tools._metadata import MetadataError
from yt_tools.search import (
    build_yt_dlp_cmd,
    results_to_markdown,
    run_search,
    slugify,
)

_QUERY = "MakeNoise Maths tutorial"

_RAW_RESULTS = [
    {
        "id": "abc123def45",
        "title": "MakeNoise Maths — Complete Walkthrough",
        "channel": "Mylar Melodies",
        "duration": 1458,  # 24:18
        "view_count": 142371,
        "upload_date": "20240812",
    },
    {
        "id": "xyz987abc12",
        "title": "Patching with Maths — Tutorial",
        "channel": "DivKid",
        "duration": 1085,  # 18:05
        "view_count": 89210,
        "upload_date": "20231104",
    },
    {
        "id": "liveSTREAM1",
        "title": "Live Patching Session",
        "channel": "Modular",
        "duration": None,
        "view_count": None,
        "upload_date": None,
        "live_status": "is_live",
    },
]


# --- build_yt_dlp_cmd (pure) -------------------------------------------------


def test_build_cmd_encodes_ytsearchN():
    cmd = build_yt_dlp_cmd(_QUERY, max_results=10, yt_dlp_bin="yt-dlp")
    # ytsearchN:<query> must appear as a single positional argument
    assert f"ytsearch10:{_QUERY}" in cmd
    assert "--dump-json" in cmd
    assert "--flat-playlist" in cmd
    assert "--no-warnings" in cmd


def test_build_cmd_respects_max():
    cmd = build_yt_dlp_cmd(_QUERY, max_results=3, yt_dlp_bin="yt-dlp")
    assert f"ytsearch3:{_QUERY}" in cmd
    assert f"ytsearch10:{_QUERY}" not in cmd


# --- slugify (pure) ----------------------------------------------------------


def test_slugify_basic_lowercase_hyphen():
    assert slugify("MakeNoise Maths tutorial") == "makenoise-maths-tutorial"


def test_slugify_strips_punctuation():
    assert slugify("Plaits @ MakeNoise!?  ") == "plaits-makenoise"


def test_slugify_cyrillic_falls_back_safely():
    # Locale-free: pure Cyrillic input strips to nothing → fallback, never raises
    out = slugify("обзор плейтс")
    assert out  # non-empty
    assert all(c.isalnum() or c == "-" for c in out)


def test_slugify_truncates_at_40():
    very_long = "a" * 100
    out = slugify(very_long)
    assert len(out) <= 40


def test_slugify_collapses_repeated_separators():
    assert slugify("foo    ---   bar") == "foo-bar"


# --- run_search (subprocess mocked) ------------------------------------------


def _proc(returncode: int, stdout: str = "", stderr: str = ""):
    return type("P", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


def test_run_search_parses_jsonl():
    jsonl = "\n".join(json.dumps(r) for r in _RAW_RESULTS)
    with patch("yt_tools.search.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools.search.subprocess.run", return_value=_proc(0, jsonl)):
        results = run_search(_QUERY, max_results=10)
    assert len(results) == 3
    assert results[0]["id"] == "abc123def45"
    assert results[2].get("live_status") == "is_live"


def test_run_search_empty_returns_empty_list():
    with patch("yt_tools.search.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools.search.subprocess.run", return_value=_proc(0, "")):
        results = run_search(_QUERY, max_results=10)
    assert results == []


def test_run_search_propagates_non_zero_exit():
    with patch("yt_tools.search.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools.search.subprocess.run", return_value=_proc(1, "", "search failed")):
        with pytest.raises(MetadataError):
            run_search(_QUERY, max_results=10)


def test_run_search_raises_when_yt_dlp_missing():
    with patch("yt_tools.search.shutil.which", return_value=None):
        with pytest.raises(MetadataError):
            run_search(_QUERY, max_results=10)


def test_run_search_skips_blank_lines():
    jsonl = json.dumps(_RAW_RESULTS[0]) + "\n\n" + json.dumps(_RAW_RESULTS[1]) + "\n"
    with patch("yt_tools.search.shutil.which", return_value="/usr/bin/yt-dlp"), \
         patch("yt_tools.search.subprocess.run", return_value=_proc(0, jsonl)):
        results = run_search(_QUERY, max_results=10)
    assert len(results) == 2


# --- results_to_markdown (pure render) ---------------------------------------


def test_render_happy_path_block_count_and_url_form():
    md = results_to_markdown(_QUERY, _RAW_RESULTS, generated="2026-05-28T14:23:11Z")
    assert f'# Search: "{_QUERY}"' in md
    assert "results: 3" in md
    assert "engine: yt-dlp ytsearch" in md
    # Numbered block headers 1..3
    assert "## 1." in md and "## 2." in md and "## 3." in md
    # Canonical watch URL form (yt-dlp's flat-playlist 'url' field is unreliable)
    assert "https://www.youtube.com/watch?v=abc123def45" in md
    assert "https://www.youtube.com/watch?v=xyz987abc12" in md


def test_render_url_is_last_field_in_each_block():
    """grep -oP 'https://[^\\s]+' relies on url being terminal — protect it."""
    md = results_to_markdown(_QUERY, _RAW_RESULTS[:1], generated="2026-05-28T14:23:11Z")
    # In the first result's block, **url:** must come after channel/duration/views/uploaded
    block = md.split("## 1.", 1)[1]
    pos_url = block.index("**url:**")
    for field in ("**channel:**", "**duration:**", "**views:**", "**uploaded:**"):
        assert block.index(field) < pos_url, f"{field} must precede url"


def test_render_live_marker():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[2]], generated="2026-05-28T14:23:11Z")
    assert "[LIVE]" in md


def test_render_duration_none_uses_dash():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[2]], generated="2026-05-28T14:23:11Z")
    # Duration None branch → em-dash placeholder, no traceback
    assert "**duration:** —" in md


def test_render_upload_date_none_omits_line():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[2]], generated="2026-05-28T14:23:11Z")
    # Missing upload_date → entire "uploaded:" line dropped (graceful)
    assert "uploaded:" not in md


def test_render_view_count_comma_grouped():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[0]], generated="2026-05-28T14:23:11Z")
    assert "142,371" in md


def test_render_duration_formatted_mmss():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[0]], generated="2026-05-28T14:23:11Z")
    assert "24:18" in md


def test_render_upload_date_iso():
    md = results_to_markdown(_QUERY, [_RAW_RESULTS[0]], generated="2026-05-28T14:23:11Z")
    assert "2024-08-12" in md


def test_render_empty_results():
    md = results_to_markdown(_QUERY, [], generated="2026-05-28T14:23:11Z")
    assert f'# Search: "{_QUERY}"' in md
    assert "results: 0" in md
    assert "No results" in md


# --- CLI: post-filter --min-duration / --max-duration ------------------------


def test_cli_min_duration_filters_shorter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", return_value=_RAW_RESULTS):
        rc = search_mod.main([_QUERY, "--min-duration", "20:00"])
    assert rc == 0
    # Find produced file in _search/
    files = list((tmp_path / "yt-cache" / "_search").glob("*.md"))
    assert len(files) == 1
    md = files[0].read_text(encoding="utf-8")
    # 24:18 walkthrough stays; 18:05 tutorial filtered; live (None duration) filtered
    assert "abc123def45" in md
    assert "xyz987abc12" not in md
    assert "liveSTREAM1" not in md


def test_cli_max_duration_filters_longer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", return_value=_RAW_RESULTS):
        rc = search_mod.main([_QUERY, "--max-duration", "20:00"])
    assert rc == 0
    files = list((tmp_path / "yt-cache" / "_search").glob("*.md"))
    md = files[0].read_text(encoding="utf-8")
    # 24:18 filtered out, 18:05 kept; live (None duration) NOT filtered by max
    assert "abc123def45" not in md
    assert "xyz987abc12" in md


# --- CLI: smoke + abort-cleanliness ------------------------------------------


def test_cli_writes_search_file_in_underscore_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", return_value=_RAW_RESULTS):
        rc = search_mod.main([_QUERY, "--max", "3"])
    assert rc == 0
    files = list((tmp_path / "yt-cache" / "_search").glob("*.md"))
    assert len(files) == 1
    # Filename: <slug>-<unix>.md
    name = files[0].name
    assert name.startswith("makenoise-maths-tutorial-")
    assert name.endswith(".md")


def test_cli_propagates_max_to_run_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", return_value=_RAW_RESULTS) as rs:
        rc = search_mod.main([_QUERY, "--max", "5"])
    assert rc == 0
    # --max plumbs into run_search call
    kwargs = rs.call_args.kwargs
    args = rs.call_args.args
    assert kwargs.get("max_results") == 5 or 5 in args


def test_cli_empty_results_exit_zero(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", return_value=[]):
        rc = search_mod.main([_QUERY])
    assert rc == 0
    files = list((tmp_path / "yt-cache" / "_search").glob("*.md"))
    assert len(files) == 1
    assert "No results" in files[0].read_text(encoding="utf-8")


def test_cli_no_empty_dir_on_search_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(search_mod, "run_search", side_effect=MetadataError("boom")):
        rc = search_mod.main([_QUERY])
    assert rc == 1
    # No file landed in _search/
    search_dir = tmp_path / "yt-cache" / "_search"
    if search_dir.exists():
        assert list(search_dir.glob("*.md")) == []
