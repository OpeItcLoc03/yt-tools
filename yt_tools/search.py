"""yt-search CLI — query → markdown list of YouTube candidates.

Phase 1 (this module): yt-dlp's native ``ytsearch`` extractor, no API key, no
config. Subprocess ``yt-dlp "ytsearchN:<query>" --dump-json --flat-playlist`` →
JSON-lines of slim per-result info-dicts → markdown blocks in
``./yt-cache/_search/<slug>-<unix>.md``.

Render style mirrors ``meta.py``/``comments.py``: numbered ``## N. title``
header, line-by-line fields, **url last** in every block so a bulk-pipeline
caller can ``grep -oP 'https://[^\\s]+'`` the file and keep result ordering
implicit in the markdown structure. The ``_search/`` prefix in cache layout
isolates these artefacts from real ``<video-id>/`` directories used by the
other CLIs.

Phase 2 (separate design loop): API-key features like caption-filter, sort,
date-range, ``yt-channel``/``yt-playlist`` — not in this module.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from yt_tools._metadata import MetadataError
from yt_tools.core import (
    force_utf8_streams,
    format_count,
    format_seconds_to_mmss,
    format_upload_date_iso,
    parse_timestamp_to_seconds,
)

DEFAULT_MAX_RESULTS = 10
SEARCH_DIR_NAME = "_search"
_SLUG_MAX = 40
_SLUG_FALLBACK = "search"
_WATCH_URL = "https://www.youtube.com/watch?v={vid}"


# --- pure helpers ------------------------------------------------------------


def slugify(query: str) -> str:
    """Lowercase, latin+digit only, hyphen-separated, truncated to 40 chars.

    Locale-free by design: unicode and Cyrillic strip out rather than transliterate
    (a transliterator would be one more dep + locale config we don't want in a
    public plugin). A query that strips to nothing falls back to ``"search"``.
    """
    lowered = query.lower()
    # Replace any run of non-[a-z0-9] with a single hyphen
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        return _SLUG_FALLBACK
    return slug[:_SLUG_MAX]


def build_yt_dlp_cmd(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    yt_dlp_bin: str = "yt-dlp",
) -> list[str]:
    """Build the ``yt-dlp`` argv for a flat search.

    ``ytsearchN:<query>`` is yt-dlp's native search extractor; ``--flat-playlist``
    keeps the result slim (no per-video info-dict round-trip), ``--no-warnings``
    silences age-gate / region noise that would land in stdout otherwise.
    """
    return [
        yt_dlp_bin,
        f"ytsearch{max_results}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-warnings",
    ]


def run_search(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    yt_dlp_bin: str = "yt-dlp",
) -> list[dict]:
    """Invoke yt-dlp search, return list of result dicts (one per JSON line).

    Raises MetadataError if yt-dlp is missing, returns non-zero, or emits a
    JSON line that won't parse.
    """
    if not shutil.which(yt_dlp_bin):
        raise MetadataError(f"yt-dlp not found on PATH (looked for {yt_dlp_bin!r})")
    cmd = build_yt_dlp_cmd(query, max_results=max_results, yt_dlp_bin=yt_dlp_bin)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MetadataError(f"yt-dlp search timed out for query {query!r}") from e
    if proc.returncode != 0:
        raise MetadataError(f"yt-dlp search failed: {proc.stderr.strip() or 'unknown error'}")

    results: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise MetadataError(f"yt-dlp returned non-JSON line: {e}") from e
    return results


# --- pure render -------------------------------------------------------------


def _result_block(idx: int, r: dict) -> list[str]:
    """One numbered result block. Url is the LAST field (bulk-grep contract)."""
    title = (r.get("title") or "(untitled)").strip()
    if r.get("live_status") == "is_live":
        title = f"{title} [LIVE]"

    lines = [f"## {idx}. {title}"]

    channel = r.get("channel") or r.get("uploader") or ""
    if channel:
        lines.append(f"- **channel:** {channel}")

    dur = r.get("duration")
    if isinstance(dur, (int, float)) and dur > 0:
        lines.append(f"- **duration:** {format_seconds_to_mmss(float(dur))}")
    else:
        lines.append("- **duration:** —")

    views = format_count(r.get("view_count"))
    if views is not None:
        lines.append(f"- **views:** {views}")

    # `--flat-playlist` on ytsearch never returns upload_date in practice
    # (YouTube only surfaces relative dates on the search page). Kept defensive
    # in case yt-dlp / YouTube ever start populating it.
    upload = format_upload_date_iso(r.get("upload_date"))
    if upload:
        lines.append(f"- **uploaded:** {upload}")

    # URL last — bulk-pipeline grep contract.
    vid = r.get("id") or ""
    url = _WATCH_URL.format(vid=vid) if vid else (r.get("url") or "")
    lines.append(f"- **url:** {url}")
    lines.append("")
    return lines


def results_to_markdown(query: str, results: list[dict], generated: str | None = None) -> str:
    """Render results as markdown. Empty list emits a ``No results`` body."""
    if generated is None:
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines: list[str] = [
        f'# Search: "{query}"',
        "",
        f"generated: {generated} · results: {len(results)} · engine: yt-dlp ytsearch",
        "",
        "---",
        "",
    ]
    if not results:
        lines.append("_No results._")
        return "\n".join(lines).rstrip() + "\n"

    for idx, r in enumerate(results, start=1):
        lines.extend(_result_block(idx, r))

    return "\n".join(lines).rstrip() + "\n"


# --- post-filters ------------------------------------------------------------


def _apply_duration_filters(
    results: list[dict],
    min_seconds: int | None,
    max_seconds: int | None,
) -> list[dict]:
    """Post-filter by duration. Results without a numeric duration are dropped
    only when a ``--min-duration`` is in effect (we can't prove they meet it);
    ``--max-duration`` alone keeps them (we can't disprove either)."""
    out: list[dict] = []
    for r in results:
        dur = r.get("duration")
        has_dur = isinstance(dur, (int, float)) and dur > 0
        if min_seconds is not None:
            if not has_dur or dur < min_seconds:
                continue
        if max_seconds is not None and has_dur and dur > max_seconds:
            continue
        out.append(r)
    return out


# --- CLI ---------------------------------------------------------------------


def _parse_duration_arg(value: str | None, flag_name: str) -> int | None:
    """Parse ``--min-duration`` / ``--max-duration``. Requires ``:`` — a bare
    integer would be ambiguous (30 = 30 seconds, not 30 minutes), so we reject
    it rather than silently disagree with the help text."""
    if value is None:
        return None
    if ":" not in value:
        raise ValueError(
            f"{flag_name} must be MM:SS or H:MM:SS (got {value!r}); "
            f"write {value}:00 for {value} minutes, or 0:{value} for {value} seconds"
        )
    return parse_timestamp_to_seconds(value)


def run(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    min_duration: str | None = None,
    max_duration: str | None = None,
    out: Path | None = None,
) -> Path:
    """Search YouTube, render markdown, write to ``yt-cache/_search/``.

    Returns the absolute path of the artefact (yt-tools stdout convention).
    """
    min_seconds = _parse_duration_arg(min_duration, "--min-duration")
    max_seconds = _parse_duration_arg(max_duration, "--max-duration")

    results = run_search(query, max_results=max_results)
    filtered = _apply_duration_filters(results, min_seconds, max_seconds)
    md = results_to_markdown(query, filtered)

    if out is None:
        slug = slugify(query)
        # Nanosecond resolution — int(time.time()) collides within a same-second
        # re-run of the same query and breaks the "never overwrites" contract.
        ts = time.time_ns()
        out = Path.cwd() / "yt-cache" / SEARCH_DIR_NAME / f"{slug}-{ts}.md"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out.resolve()


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="yt-search",
        description="Search YouTube via yt-dlp; emit a markdown list of candidates "
        "in ./yt-cache/_search/<slug>-<unix>.md.",
    )
    parser.add_argument("query", help="Search query (free text)")
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        dest="max_results",
        help=f"Max results to fetch (default: {DEFAULT_MAX_RESULTS}).",
    )
    parser.add_argument(
        "--min-duration",
        default=None,
        help="Post-filter: drop results shorter than MM:SS (or H:MM:SS).",
    )
    parser.add_argument(
        "--max-duration",
        default=None,
        help="Post-filter: drop results longer than MM:SS (or H:MM:SS).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: ./yt-cache/_search/<slug>-<unix>.md).",
    )
    args = parser.parse_args(argv)

    try:
        path = run(
            args.query,
            max_results=args.max_results,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            out=args.out,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(str(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
