"""Tests for yt-frames subprocess error propagation."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from yt_tools import frames as frames_mod


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_ensure_source_mp4_missing_ffmpeg_raises_explicit_error(tmp_path: Path):
    # Reproduce reported failure: ffmpeg absent on PATH → user got
    # 'yt-dlp source download failed:' with empty body. After fix, ffmpeg must
    # be pre-checked so the error names ffmpeg, not yt-dlp.
    def which(name: str):
        return None if name == "ffmpeg" else "/fake/path/" + name

    with patch.object(frames_mod.shutil, "which", side_effect=which):
        with pytest.raises(RuntimeError, match=r"ffmpeg"):
            frames_mod._ensure_source_mp4("https://youtu.be/x", tmp_path / "src.mp4")


def test_ensure_source_mp4_yt_dlp_failure_includes_stderr(tmp_path: Path):
    # yt-dlp exits non-zero with stderr — error message must surface it.
    with patch.object(frames_mod.shutil, "which", return_value="/fake/bin"), \
         patch.object(frames_mod.subprocess, "run", return_value=_completed(1, stderr="ERROR: Private video")):
        with pytest.raises(RuntimeError, match=r"Private video"):
            frames_mod._ensure_source_mp4("https://youtu.be/x", tmp_path / "src.mp4")


def test_subprocess_failure_with_empty_stderr_includes_stdout_or_no_output_hint(tmp_path: Path):
    # When both stderr and stdout are empty, message must say so explicitly
    # instead of trailing the prefix with a bare colon and nothing.
    with patch.object(frames_mod.shutil, "which", return_value="/fake/bin"), \
         patch.object(frames_mod.subprocess, "run", return_value=_completed(1, stdout="", stderr="")):
        with pytest.raises(RuntimeError) as ei:
            frames_mod._ensure_source_mp4("https://youtu.be/x", tmp_path / "src.mp4")
    msg = str(ei.value)
    # The message must not end with a bare colon-and-nothing — that was the original bug.
    assert not msg.rstrip().endswith(":")
    assert "exit 1" in msg or "no output" in msg.lower()


def test_subprocess_failure_with_only_stdout_surfaces_stdout(tmp_path: Path):
    # yt-dlp occasionally writes diagnostic info to stdout. Falling back to stdout
    # when stderr is empty keeps the user from losing the cause.
    with patch.object(frames_mod.shutil, "which", return_value="/fake/bin"), \
         patch.object(frames_mod.subprocess, "run", return_value=_completed(1, stdout="HTTP 403 Forbidden", stderr="")):
        with pytest.raises(RuntimeError, match=r"403 Forbidden"):
            frames_mod._ensure_source_mp4("https://youtu.be/x", tmp_path / "src.mp4")
