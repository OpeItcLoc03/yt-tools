"""yt-frames CLI — extract frames at given timestamps, intervals, or scene boundaries.

Three modes (mutually exclusive):
  --timestamps 1:23,4:56     (default if --timestamps is given)
  --mode interval --interval 30s
  --mode scene  --scene-threshold 27

Source-mp4 cache: the first call for a URL downloads ``source.mp4`` (720p) into
``./yt-cache/<vid>/``; subsequent calls reuse the local file via ``ffmpeg -ss``.
Use ``--no-cache-source`` to stream the source via ``yt-dlp -g | ffmpeg`` instead.

Each extracted frame prints ``Wrote: <abs path>`` on its own stdout line so callers
can pipe / scrape without parsing a summary at the end.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from yt_tools._metadata import MetadataError, fetch_video_metadata
from yt_tools.core import (
    cache_dir_for,
    extract_video_id,
    force_utf8_streams,
    format_seconds_for_filename,
    interval_timestamps,
    parse_timestamp_to_seconds,
)

SOURCE_FORMAT_SPEC = "bv*[height<=720]+ba/b[height<=720]"
DEFAULT_SCENE_THRESHOLD = 27.0
_INTERVAL_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(s|sec|m|min|h)?$", re.IGNORECASE)


def parse_interval(spec: str) -> float:
    """Parse ``30s`` / ``1m`` / ``2h`` / bare seconds into a float number of seconds."""
    m = _INTERVAL_RE.match(spec.strip())
    if not m:
        raise ValueError(f"invalid interval: {spec!r}")
    value = float(m.group(1))
    unit = (m.group(2) or "s").lower()
    if unit in ("s", "sec"):
        return value
    if unit in ("m", "min"):
        return value * 60.0
    if unit == "h":
        return value * 3600.0
    raise ValueError(f"invalid interval unit: {unit!r}")


def _require_bin(name: str) -> None:
    if not shutil.which(name):
        raise RuntimeError(f"{name} not found on PATH")


def _format_subprocess_failure(proc: subprocess.CompletedProcess, label: str) -> str:
    """Build a self-contained error message — exit code + stderr/stdout tail, or an explicit no-output hint."""
    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    parts = [f"{label} failed (exit {proc.returncode})"]
    if stderr:
        parts.append(f"stderr: {stderr[-500:]}")
    if stdout and not stderr:
        parts.append(f"stdout: {stdout[-500:]}")
    if not stderr and not stdout:
        parts.append("no output captured — check binary install / PATH / network")
    return " | ".join(parts)


def _ensure_source_mp4(url: str, dest: Path, yt_dlp_bin: str = "yt-dlp") -> Path:
    """Download the source video to ``dest`` if it doesn't already exist. Returns ``dest``."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    _require_bin(yt_dlp_bin)
    # yt-dlp needs ffmpeg for muxing bestvideo+bestaudio into mp4. Pre-check so a
    # missing-ffmpeg failure surfaces as "ffmpeg not found on PATH" rather than an
    # opaque "yt-dlp source download failed:" with empty stderr.
    _require_bin("ffmpeg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            yt_dlp_bin,
            "-f", SOURCE_FORMAT_SPEC,
            "--merge-output-format", "mp4",
            "-o", str(dest),
            "--no-progress",
            url,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(_format_subprocess_failure(proc, "yt-dlp source download"))
    return dest


def _ffmpeg_extract_from_file(source: Path, seconds: float, out_path: Path, ffmpeg_bin: str = "ffmpeg") -> None:
    """Extract a single frame from a local file at ``seconds`` into ``out_path``."""
    _require_bin(ffmpeg_bin)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-ss", f"{seconds:.3f}",
            "-i", str(source),
            "-vframes", "1",
            "-q:v", "2",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(_format_subprocess_failure(proc, f"ffmpeg extract at {seconds}s"))


def _ffmpeg_extract_streaming(
    url: str,
    seconds: float,
    out_path: Path,
    yt_dlp_bin: str = "yt-dlp",
    ffmpeg_bin: str = "ffmpeg",
) -> None:
    """Stream the source via ``yt-dlp -g`` and grab one frame with ``ffmpeg -ss``."""
    _require_bin(yt_dlp_bin)
    _require_bin(ffmpeg_bin)
    g = subprocess.run(
        [yt_dlp_bin, "-f", SOURCE_FORMAT_SPEC, "-g", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if g.returncode != 0:
        raise RuntimeError(_format_subprocess_failure(g, "yt-dlp -g"))
    direct_url = g.stdout.strip().splitlines()[0]
    if not direct_url:
        raise RuntimeError("yt-dlp -g returned no URL")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-ss", f"{seconds:.3f}",
            "-i", direct_url,
            "-vframes", "1",
            "-q:v", "2",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(_format_subprocess_failure(proc, f"ffmpeg streaming extract at {seconds}s"))


def _detect_scene_timestamps(source: Path, threshold: float) -> list[float]:
    """Use PySceneDetect to find scene-boundary timestamps (seconds)."""
    from scenedetect import ContentDetector, detect

    scenes = detect(str(source), ContentDetector(threshold=threshold))
    return [s[0].get_seconds() for s in scenes]


def run(
    url: str,
    out_dir: Path | None = None,
    timestamps: list[float] | None = None,
    mode: str = "timestamps",
    interval: float | None = None,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    no_cache_source: bool = False,
) -> list[Path]:
    """Extract frames per the chosen mode. Returns the list of written file paths."""
    extract_video_id(url)  # validate
    if out_dir is None:
        out_dir = cache_dir_for(url) / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out_dir.parent

    if mode == "timestamps":
        if not timestamps:
            raise ValueError("mode=timestamps requires --timestamps")
        seconds_list = list(timestamps)
    elif mode == "interval":
        if not interval:
            raise ValueError("mode=interval requires --interval")
        meta = fetch_video_metadata(url)
        seconds_list = interval_timestamps(meta["duration"], interval)
    elif mode == "scene":
        if no_cache_source:
            raise ValueError("scene mode requires a downloaded source (drop --no-cache-source)")
        source = _ensure_source_mp4(url, cache_root / "source.mp4")
        seconds_list = _detect_scene_timestamps(source, scene_threshold)
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    if not seconds_list:
        return []

    written: list[Path] = []
    if no_cache_source:
        for s in seconds_list:
            out_path = out_dir / f"frame_{format_seconds_for_filename(s)}.jpg"
            _ffmpeg_extract_streaming(url, s, out_path)
            written.append(out_path.resolve())
            print(f"Wrote: {out_path.resolve()}")
    else:
        source = _ensure_source_mp4(url, cache_root / "source.mp4")
        for s in seconds_list:
            out_path = out_dir / f"frame_{format_seconds_for_filename(s)}.jpg"
            _ffmpeg_extract_from_file(source, s, out_path)
            written.append(out_path.resolve())
            print(f"Wrote: {out_path.resolve()}")
    return written


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="yt-frames",
        description="Extract frames from a YouTube video at given timestamps / intervals / scene boundaries.",
    )
    parser.add_argument("url", help="YouTube URL or bare video id")
    parser.add_argument("--out", type=Path, default=None, help="Output dir (default: ./yt-cache/<vid>/frames/)")
    parser.add_argument(
        "--timestamps",
        default=None,
        help="Comma-separated mm:ss list; sets mode=timestamps. Example: 1:23,4:56,12:30",
    )
    parser.add_argument(
        "--mode",
        choices=["timestamps", "interval", "scene"],
        default=None,
        help="Extraction mode (auto: 'timestamps' if --timestamps given, else required).",
    )
    parser.add_argument("--interval", default=None, help="For --mode interval. Example: 30s / 1m / 2h")
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_THRESHOLD,
        help=f"PySceneDetect ContentDetector threshold (default {DEFAULT_SCENE_THRESHOLD}).",
    )
    parser.add_argument(
        "--no-cache-source",
        action="store_true",
        help="Stream source via yt-dlp -g | ffmpeg instead of caching source.mp4 on disk.",
    )
    args = parser.parse_args(argv)

    mode = args.mode or ("timestamps" if args.timestamps else None)
    if mode is None:
        parser.error("must give --timestamps or --mode {interval|scene}")

    timestamps: list[float] | None = None
    if args.timestamps:
        try:
            timestamps = [parse_timestamp_to_seconds(t) for t in args.timestamps.split(",") if t.strip()]
        except ValueError as e:
            parser.error(str(e))

    interval_seconds: float | None = None
    if args.interval:
        try:
            interval_seconds = parse_interval(args.interval)
        except ValueError as e:
            parser.error(str(e))

    try:
        run(
            args.url,
            out_dir=args.out,
            timestamps=timestamps,
            mode=mode,
            interval=interval_seconds,
            scene_threshold=args.scene_threshold,
            no_cache_source=args.no_cache_source,
        )
    except (ValueError, RuntimeError, MetadataError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
