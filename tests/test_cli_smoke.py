"""End-to-end CLI smoke tests with subprocess + youtube-transcript-api mocked.

We don't hit the real network — these tests verify the wiring (argparse parsing,
output paths, stdout contract) without touching yt-dlp / ffmpeg / YouTube.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from yt_tools import cli as umbrella_cli
from yt_tools import frames as frames_mod
from yt_tools import transcript as transcript_mod
from yt_tools.markdown import Snippet


# ---- yt-transcript ----------------------------------------------------------


def test_yt_transcript_writes_file_and_prints_path(tmp_path, monkeypatch, capsys):
    out = tmp_path / "transcript.md"
    fake_snippets = ([Snippet("hello", 0.0, 2.0), Snippet("world", 60.0, 2.0)], "en")
    fake_meta = {"title": "Demo", "channel": "Chan", "duration": 100, "url": "https://youtu.be/abcDEF12345"}

    with patch.object(transcript_mod, "_fetch_snippets", return_value=fake_snippets), \
         patch.object(transcript_mod, "fetch_video_metadata", return_value=fake_meta):
        rc = transcript_mod.main(["https://youtu.be/abcDEF12345", "--out", str(out)])

    assert rc == 0
    captured = capsys.readouterr()
    last_line = captured.out.strip().splitlines()[-1]
    assert last_line == str(out.resolve())
    body = out.read_text(encoding="utf-8")
    assert "# Demo" in body
    assert "hello" in body and "world" in body
    assert "[0:00]" in body and "[1:00]" in body


def test_yt_transcript_distill_emits_hint_on_stderr(tmp_path, capsys):
    out = tmp_path / "t.md"
    fake_snippets = ([Snippet("hello", 0.0)], "en")
    fake_meta = {"title": "T", "channel": "", "duration": 5, "url": "u"}
    with patch.object(transcript_mod, "_fetch_snippets", return_value=fake_snippets), \
         patch.object(transcript_mod, "fetch_video_metadata", return_value=fake_meta):
        rc = transcript_mod.main(["https://youtu.be/abcDEF12345", "--out", str(out), "--distill"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "distill-hint" in captured.err
    assert "mcp__interns__transcript_distill" in captured.err


# ---- yt-frames --------------------------------------------------------------


def test_yt_frames_timestamps_mode_writes_each_frame(tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "frames"

    def fake_ensure(url, dest, yt_dlp_bin="yt-dlp"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake-mp4")
        return dest

    def fake_extract(source, seconds, out_path, ffmpeg_bin="ffmpeg"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake-jpg")

    with patch.object(frames_mod, "_ensure_source_mp4", side_effect=fake_ensure), \
         patch.object(frames_mod, "_ffmpeg_extract_from_file", side_effect=fake_extract):
        rc = frames_mod.main([
            "https://youtu.be/abcDEF12345",
            "--out", str(out_dir),
            "--timestamps", "1:23,4:56",
        ])

    assert rc == 0
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert len(out_lines) == 2
    assert all(line.startswith("Wrote: ") for line in out_lines)
    assert (out_dir / "frame_0123.jpg").exists()
    assert (out_dir / "frame_0456.jpg").exists()


def test_yt_frames_requires_mode(capsys):
    with pytest.raises(SystemExit):
        frames_mod.main(["https://youtu.be/abcDEF12345"])
    captured = capsys.readouterr()
    assert "--timestamps" in captured.err or "--mode" in captured.err


def test_yt_frames_interval_mode_uses_metadata_duration(tmp_path, capsys):
    out_dir = tmp_path / "frames"
    fake_meta = {"title": "T", "channel": "", "duration": 100, "url": "u"}

    def fake_ensure(url, dest, yt_dlp_bin="yt-dlp"):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake-mp4")
        return dest

    def fake_extract(source, seconds, out_path, ffmpeg_bin="ffmpeg"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"x")

    with patch.object(frames_mod, "fetch_video_metadata", return_value=fake_meta), \
         patch.object(frames_mod, "_ensure_source_mp4", side_effect=fake_ensure), \
         patch.object(frames_mod, "_ffmpeg_extract_from_file", side_effect=fake_extract):
        rc = frames_mod.main([
            "https://youtu.be/abcDEF12345",
            "--out", str(out_dir),
            "--mode", "interval",
            "--interval", "30s",
        ])
    assert rc == 0
    # 0, 30, 60, 90 — four frames in a 100s video at 30s interval
    assert len(list(out_dir.glob("frame_*.jpg"))) == 4


# ---- yt-tools cache ---------------------------------------------------------


def test_yt_tools_cache_list_empty(tmp_path, capsys):
    rc = umbrella_cli.main(["cache", "list", "--base", str(tmp_path)])
    assert rc == 0
    assert "(empty:" in capsys.readouterr().out


def test_yt_tools_cache_list_reports_entries(tmp_path, capsys):
    (tmp_path / "yt-cache" / "abc12345").mkdir(parents=True)
    (tmp_path / "yt-cache" / "abc12345" / "f.bin").write_bytes(b"x" * 2048)
    rc = umbrella_cli.main(["cache", "list", "--base", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "abc12345" in out
    assert "total: 1 videos" in out


def test_yt_tools_cache_prune_noop_when_empty(tmp_path, capsys):
    rc = umbrella_cli.main(["cache", "prune", "--base", str(tmp_path), "--older-than", "1d"])
    assert rc == 0
    assert "(nothing to prune" in capsys.readouterr().out
