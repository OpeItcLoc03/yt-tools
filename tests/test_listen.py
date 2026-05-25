"""Tests for yt-listen — pipeline smoke (mocked) + unit tests for parsers/formatters."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yt_tools import listen as listen_mod


# --------------------------------------------------------------------------- #
# Unit: timestamp parsing                                                     #
# --------------------------------------------------------------------------- #

class TestParseTimestampToSecondsFloat:
    def test_bare_seconds(self):
        assert listen_mod.parse_timestamp_to_seconds_float("45") == 45.0

    def test_mmss_int(self):
        assert listen_mod.parse_timestamp_to_seconds_float("1:23") == 83.0

    def test_mmss_fractional(self):
        assert listen_mod.parse_timestamp_to_seconds_float("1:23.5") == 83.5

    def test_hhmmss(self):
        assert listen_mod.parse_timestamp_to_seconds_float("1:02:03") == 3723.0

    def test_hhmmss_fractional(self):
        assert listen_mod.parse_timestamp_to_seconds_float("0:00:10.25") == 10.25

    def test_too_many_parts(self):
        with pytest.raises(ValueError, match=r"too many parts"):
            listen_mod.parse_timestamp_to_seconds_float("1:2:3:4")

    def test_non_numeric(self):
        with pytest.raises(ValueError, match=r"non-numeric"):
            listen_mod.parse_timestamp_to_seconds_float("a:b")


# --------------------------------------------------------------------------- #
# Unit: duration parsing                                                      #
# --------------------------------------------------------------------------- #

class TestParseDuration:
    def test_bare_seconds(self):
        assert listen_mod.parse_duration("30") == 30.0

    def test_seconds_suffix(self):
        assert listen_mod.parse_duration("10s") == 10.0

    def test_minutes_suffix(self):
        assert listen_mod.parse_duration("2m") == 120.0

    def test_fractional(self):
        assert listen_mod.parse_duration("0.5s") == 0.5

    def test_invalid(self):
        with pytest.raises(ValueError, match=r"invalid duration"):
            listen_mod.parse_duration("forever")


# --------------------------------------------------------------------------- #
# Unit: feature-formatting (markdown structure)                               #
# --------------------------------------------------------------------------- #

def _fake_librosa_features():
    return {
        "rms_mean": 0.142,
        "rms_max": 0.187,
        "centroid_mean": 2840.0,
        "rolloff_mean": 6200.0,
        "bandwidth_mean": 1800.0,
        "flatness_mean": 0.21,
        "zcr_mean": 0.094,
        # chroma_mean: 12 values, A=index 9 highest.
        "chroma_mean": [0.05, 0.04, 0.06, 0.03, 0.07, 0.04, 0.05, 0.06, 0.04, 0.18, 0.05, 0.06],
        "chroma_order": [9, 4, 7, 2, 11, 8, 6, 0, 10, 5, 1, 3],
        "peaks": [(110.0, 1.5), (220.0, 1.2), (440.0, 0.9), (2840.0, 0.7), (8200.0, 0.4)],
        "harmonic_fraction": 0.64,
        "percussive_fraction": 0.36,
    }


def _fake_bpm_result():
    return {
        "basic_info": {"bpm": 128.0, "bpm_confidence": 0.87, "key": "A minor", "key_confidence": 0.91},
        "chord_progression": {"chords": ["Am", "F", "C", "G"]},
        "structure": {"sections": [
            {"label": "intro", "start": 0.0, "end": 8.0},
            {"label": "verse", "start": 8.0, "end": 30.0},
        ]},
    }


class TestFormatFeaturesMarkdown:
    def test_all_required_sections_present_with_bpm_detector(self):
        md = listen_mod.format_features_markdown(
            timestamp_seconds=150.0,
            duration_seconds=30.0,
            librosa_features=_fake_librosa_features(),
            bpm_result=_fake_bpm_result(),
            fallback_basic=None,
        )
        # Header with mm:ss
        assert "# Audio features @ 2:30 (duration 30s)" in md
        # All six required sections
        assert "## Tempo + key" in md
        assert "## Chord progression" in md
        assert "## Structure" in md
        assert "## Spectral features (librosa)" in md
        assert "## Peak frequencies" in md
        assert "## Harmonic / percussive split" in md
        # Tempo+key values surfaced
        assert "128.0 BPM" in md
        assert "A minor" in md
        # Chord progression rendered as arrow-chain
        assert "Am → F → C → G" in md
        # Structure rendered
        assert "intro" in md and "verse" in md
        # Spectral values
        assert "2840 Hz" in md
        # Top-3 chroma — A should be ranked first
        assert "1. A —" in md
        # Peaks
        assert "110 Hz" in md and "A2" in md  # note label rendered
        # HPSS split
        assert "Harmonic energy: 64%" in md
        assert "Percussive energy: 36%" in md

    def test_required_sections_present_with_fallback(self):
        # Sections still rendered even when bpm_detector dep is unavailable.
        md = listen_mod.format_features_markdown(
            timestamp_seconds=30.0,
            duration_seconds=10.0,
            librosa_features=_fake_librosa_features(),
            bpm_result=None,
            fallback_basic={"tempo_bpm": 120.0, "tempo_confidence": None, "key": "C major", "key_confidence": 0.85},
        )
        assert "## Tempo + key" in md
        assert "## Chord progression" in md
        assert "## Structure" in md
        assert "## Spectral features (librosa)" in md
        assert "## Peak frequencies" in md
        assert "## Harmonic / percussive split" in md
        # Fallback tempo + key surfaced
        assert "120.0 BPM" in md
        assert "C major" in md
        # n/a markers for absent bpm-detector sections
        assert "_n/a" in md  # at least once for chord progression and structure


class TestFormatHelpers:
    def test_chord_progression_dict_with_sequence(self):
        assert listen_mod._format_chord_progression(
            {"chord_progression": {"sequence": ["Dm", "G7", "Cmaj7"]}}
        ) == "Dm → G7 → Cmaj7"

    def test_chord_progression_list_of_dicts(self):
        result = listen_mod._format_chord_progression({"chord_progression": [
            {"chord": "C", "start": 0, "end": 1},
            {"chord": "Am", "start": 1, "end": 2},
        ]})
        assert result == "C → Am"

    def test_chord_progression_none_when_missing(self):
        assert listen_mod._format_chord_progression(None) is None
        assert listen_mod._format_chord_progression({}) is None
        assert listen_mod._format_chord_progression({"chord_progression": []}) is None

    def test_structure_sections(self):
        result = listen_mod._format_structure({"structure": {"sections": [
            {"label": "verse", "start": 0.0, "end": 16.0},
            {"label": "chorus", "start": 16.0, "end": 32.0},
        ]}})
        assert "verse" in result and "chorus" in result
        assert "0.0s" in result and "32.0s" in result

    def test_structure_none_when_missing(self):
        assert listen_mod._format_structure(None) is None
        assert listen_mod._format_structure({}) is None

    def test_hz_to_note(self):
        # A4 = 440 Hz is the canonical anchor.
        assert listen_mod._hz_to_note(440.0) == "A4"
        # A2 = 110 Hz
        assert listen_mod._hz_to_note(110.0) == "A2"
        # 0 Hz is the unknown case
        assert listen_mod._hz_to_note(0.0) == "?"


# --------------------------------------------------------------------------- #
# Smoke: pipeline reaches each stage (ffmpeg + librosa + bpm-detector mocked) #
# --------------------------------------------------------------------------- #

def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["ffmpeg"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_pipeline_smoke(tmp_path, capsys, monkeypatch):
    """Full pipeline with everything stubbed — verifies stdout contract + file plumbing."""
    import numpy as np

    cache_dir = tmp_path / "yt-cache" / "dQw4w9WgXcQ"
    audio_dir = cache_dir / "audio"

    # Fake _ensure_source_mp4 — pretend the cache file exists, never run yt-dlp.
    def fake_ensure(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 16)
        return dest

    # Fake ffmpeg WAV extract — touch the output file.
    def fake_wav_extract(source, seconds, duration, sample_rate, out_path, ffmpeg_bin="ffmpeg"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")  # bogus, never read

    # Fake librosa.load → return a tiny array (1 second of silence).
    def fake_load(path, sr=22050, mono=True):
        return np.zeros(sr, dtype=np.float32), sr

    monkeypatch.setattr(listen_mod, "_ensure_source_mp4", fake_ensure)
    monkeypatch.setattr(listen_mod, "_ffmpeg_extract_wav", fake_wav_extract)
    monkeypatch.setattr(listen_mod, "_librosa_features", lambda y, sr: _fake_librosa_features())
    monkeypatch.setattr(listen_mod, "_bpm_detector_analyse", lambda *a, **k: _fake_bpm_result())
    monkeypatch.setattr(listen_mod, "_render_spectrogram", lambda y, sr, out_path, **kw: out_path.write_bytes(b"\x89PNG"))
    monkeypatch.setattr(listen_mod, "_render_chroma", lambda y, sr, out_path: out_path.write_bytes(b"\x89PNG"))

    import librosa
    monkeypatch.setattr(librosa, "load", fake_load)

    written = listen_mod.run(
        "https://youtu.be/dQw4w9WgXcQ",
        out_dir=audio_dir,
        timestamps=[30.0, 60.0],
        mode="timestamps",
        duration=10.0,
        sample_rate=22050,
    )

    # 3 artifacts per timestamp × 2 timestamps = 6 paths.
    assert len(written) == 6
    # Every path printed on its own "Wrote: " stdout line.
    captured = capsys.readouterr().out
    wrote_lines = [line for line in captured.splitlines() if line.startswith("Wrote: ")]
    assert len(wrote_lines) == 6
    for p in written:
        assert any(str(p) in line for line in wrote_lines)
    # Every artifact exists on disk.
    for p in written:
        assert p.exists()
    # Filename stems use the canonical mmss layout.
    names = {p.name for p in written}
    assert "audio_0030.wav" in names
    assert "spectrogram_0030.png" in names
    assert "features_0030.md" in names
    assert "audio_0100.wav" in names


def test_run_no_wav_deletes_file(tmp_path, capsys, monkeypatch):
    """--no-wav: WAV is created (needed for bpm_detector analyse) then deleted."""
    import numpy as np

    audio_dir = tmp_path / "yt-cache" / "dQw4w9WgXcQ" / "audio"

    def fake_ensure(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00")
        return dest

    def fake_wav_extract(source, seconds, duration, sample_rate, out_path, ffmpeg_bin="ffmpeg"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF")

    monkeypatch.setattr(listen_mod, "_ensure_source_mp4", fake_ensure)
    monkeypatch.setattr(listen_mod, "_ffmpeg_extract_wav", fake_wav_extract)
    monkeypatch.setattr(listen_mod, "_librosa_features", lambda y, sr: _fake_librosa_features())
    monkeypatch.setattr(listen_mod, "_bpm_detector_analyse", lambda *a, **k: _fake_bpm_result())
    monkeypatch.setattr(listen_mod, "_render_spectrogram", lambda y, sr, out_path, **kw: out_path.write_bytes(b"\x89PNG"))

    import librosa
    monkeypatch.setattr(librosa, "load", lambda path, sr=22050, mono=True: (np.zeros(sr, dtype=np.float32), sr))

    written = listen_mod.run(
        "https://youtu.be/dQw4w9WgXcQ",
        out_dir=audio_dir,
        timestamps=[30.0],
        mode="timestamps",
        duration=10.0,
        no_wav=True,
    )

    # WAV not in returned paths, but spectrogram + features are.
    names = {p.name for p in written}
    assert "audio_0030.wav" not in names
    assert "spectrogram_0030.png" in names
    assert "features_0030.md" in names
    # WAV file deleted from disk.
    assert not (audio_dir / "audio_0030.wav").exists()


def test_bpm_detector_fallback_when_unavailable(tmp_path, capsys, monkeypatch):
    """When bpm_detector returns None, fallback Krumhansl-Schmuckler kicks in and markdown still has all sections."""
    import numpy as np

    audio_dir = tmp_path / "yt-cache" / "dQw4w9WgXcQ" / "audio"

    def fake_ensure(url, dest, **kw):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00")
        return dest

    def fake_wav_extract(source, seconds, duration, sample_rate, out_path, ffmpeg_bin="ffmpeg"):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF")

    monkeypatch.setattr(listen_mod, "_ensure_source_mp4", fake_ensure)
    monkeypatch.setattr(listen_mod, "_ffmpeg_extract_wav", fake_wav_extract)
    monkeypatch.setattr(listen_mod, "_librosa_features", lambda y, sr: _fake_librosa_features())
    monkeypatch.setattr(listen_mod, "_bpm_detector_analyse", lambda *a, **k: None)
    monkeypatch.setattr(listen_mod, "_librosa_fallback_basic", lambda y, sr: {
        "tempo_bpm": 120.0, "tempo_confidence": None, "key": "C major", "key_confidence": 0.78,
    })
    monkeypatch.setattr(listen_mod, "_render_spectrogram", lambda y, sr, out_path, **kw: out_path.write_bytes(b"\x89PNG"))

    import librosa
    monkeypatch.setattr(librosa, "load", lambda path, sr=22050, mono=True: (np.zeros(sr, dtype=np.float32), sr))

    listen_mod.run(
        "https://youtu.be/dQw4w9WgXcQ",
        out_dir=audio_dir,
        timestamps=[30.0],
        mode="timestamps",
        duration=10.0,
    )

    md = (audio_dir / "features_0030.md").read_text(encoding="utf-8")
    assert "120.0 BPM" in md
    assert "C major" in md
    # Required sections still present
    assert "## Tempo + key" in md
    assert "## Chord progression" in md
    assert "## Structure" in md


def test_run_rejects_empty_timestamps():
    with pytest.raises(ValueError, match=r"mode=timestamps requires --timestamps"):
        listen_mod.run("https://youtu.be/dQw4w9WgXcQ", timestamps=[], mode="timestamps")


def test_run_rejects_unknown_mode():
    with pytest.raises(ValueError, match=r"unknown mode"):
        listen_mod.run("https://youtu.be/dQw4w9WgXcQ", mode="wat", timestamps=[1.0])
