# yt-tools

CLI suite for **iterative agent-driven YouTube watching**. The agent reads the
transcript, decides which moments matter, then pulls only those frames or
audio FFT slices — no bulk download, no JSON soup, no MCP scaffolding.

Eight CLIs, one cache, stdout-friendly absolute paths so the caller never
has to guess where the artefact landed:

- `yt-search` — query → markdown list of candidate videos via yt-dlp's
  native `ytsearch` extractor. The entry-point when the user hasn't named
  a URL yet; pick one and continue into the other CLIs. Zero config, no
  API key.
- `yt-transcript` — clean markdown transcript with metadata header and
  `[mm:ss]` paragraph anchors copy-paste-friendly for `--timestamps`.
- `yt-meta` — full metadata as markdown: description, chapters (`[mm:ss]`
  anchors), most-replayed heatmap, view/like/comment counts, tags, subtitle
  languages. Zero added cost — reuses the same `yt-dlp --dump-json` call.
- `yt-comments` — comments as markdown (top-level + nested replies). A
  **separate paginated scrape** (can take minutes on viral videos), so it is
  capped at the top 50 by default; raise with `--max`. Call it deliberately.
- `yt-frames` — targeted frame extraction by timestamp, scene-detect, or
  fixed interval.
- `yt-ocr` — OCR over cached frames (RapidOCR PP-OCRv5 via onnxruntime) →
  `[mm:ss]` markdown blocks. The fallback for silent-with-text videos
  where the transcript is empty and content lives in burned-in overlay
  text (schematic labels, chord matrices, parameter walkthroughs). Needs
  the `[ocr]` extra.
- `yt-listen` — FFT audio analysis: per-timestamp clip + mel-spectrogram PNG +
  features `.md` with BPM, key, chord progression, and spectral statistics.
- `yt-watch` — combined transcript + scene-frames in one `.md` with
  `![](frames/...)` sidecar embeds.
- `yt-tools cache list | prune` — manage the source-mp4 cache.

## Installation

`yt-tools` v1 ships **via a Claude Code plugin** (recommended for agent
workflows) or **directly from this Git repository** (for standalone CLI
use in any environment). PyPI distribution is deferred to a future release.

### As a Claude Code plugin (recommended for agent workflows)

```text
/plugin marketplace add kzntsv-dev/claude-plugins
/plugin install yt-tools@opeitcloc03-claude-plugins
```

The plugin's `SessionStart` hook runs
`pipx install --force "$CLAUDE_PLUGIN_ROOT"` on the first session after
install, exposing `yt-search`, `yt-transcript`, `yt-meta`, `yt-comments`,
`yt-frames`, `yt-ocr`, `yt-listen`, `yt-watch`, `yt-tools` (and a shimmed
`yt-dlp`) in `~/.local/bin/`. The bundled `using-yt-tools` skill
orchestrates the flows (discovery search / iterative watch / targeted
frames / audio analysis / metadata / comments / OCR) for the agent. The
hook installs the `[full]` extra by default; the `[ocr]` extra (RapidOCR
+ onnxruntime) is opt-in — see the OCR section below.

The plugin marketplace catalog lives at
[`kzntsv-dev/claude-plugins`](https://github.com/kzntsv-dev/claude-plugins);
this repository at [`kzntsv-dev/yt-tools`](https://github.com/kzntsv-dev/yt-tools).

### Standalone CLI (any environment)

Install directly from this Git repo via [`pipx`](https://pipx.pypa.io/):

```bash
# 1. bootstrap pipx (one-time per user)
python -m pip install --user pipx
python -m pipx ensurepath          # adds ~/.local/bin to PATH; restart shell after

# 2. install yt-tools (core) from this repo
pipx install git+https://github.com/kzntsv-dev/yt-tools.git

# 3. (optional) install the [full] extra for chord progression + structure analysis
pipx install "git+https://github.com/kzntsv-dev/yt-tools.git#egg=yt-tools[full]"
```

Core install gets you `yt-listen` with `librosa`'s `beat_track` +
Krumhansl-Schmuckler key estimation. The `[full]` extra pulls in
[`bpm-detector`](https://github.com/libraz/bpm-detector) (VCS dep, not yet
on PyPI) for richer features per timestamp — chord progression,
structural segments, refined BPM, confidence-scored key. Without
`[full]`, `yt-listen` gracefully falls back to librosa-only basics.

### ffmpeg (external binary, all install paths)

`yt-tools` shells out to `ffmpeg` for source-video caching and per-clip
extraction. Install via your OS package manager:

| OS | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` |
| macOS | `brew install ffmpeg` |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |
| Linux (Fedora/RHEL) | `sudo dnf install ffmpeg` |

> **Windows-gotcha.** `winget install Gyan.FFmpeg` writes `ffmpeg.exe` into
> the per-user PATH, which the *current* shell session does not re-read.
> Either restart the terminal, or prepend the install directory to `$env:PATH`
> for the current session.

### Plugin hook environment variables

The bundled `SessionStart` hook honours two environment variables, both
optional:

| Var | Effect |
|---|---|
| `YT_TOOLS_PYTHON` | Full path to a Python interpreter. Used both for the pre-install health probe and forwarded to `pipx install --python` so the venv is built with this exact interpreter. Set this when your default Python is broken (e.g. `uv` toolchain drift surfacing `SRE module mismatch` from `re.compile`). |
| `CLAUDE_PLUGIN_ROOT` | Set automatically by Claude Code to the plugin's local clone; the hook uses it as the install source. Not for manual override. |

Before each install, the hook probes the candidate interpreter with
`python -c "import re; re.compile('x')"`. If the probe crashes (broken
stdlib), the hook refuses to install and preserves any existing pipx-venv
rather than replacing it with a broken one.

## Quick start

The CLIs are designed for an **iterative** loop: cheap transcript first,
then targeted heavy fetches only at the timestamps that mattered.

### Flow 0 — discovery

```bash
# Find candidate videos when you don't have a URL yet.
yt-search "MakeNoise Maths tutorial"
# → ./yt-cache/_search/makenoise-maths-tutorial-1748443391123456789.md

yt-search "drum tutorial" --max 5                    # cap result count
yt-search "long-form review" --min-duration 20:00    # skip shorts
yt-search "explainer" --max-duration 10:00           # skip long-form
```

The result file is per-result blocks — title, channel, duration, views,
URL (last field per block, so `grep -oP 'https://[^\s]+'` peels the raw
URL list). Pick one and continue into Flow 1 (`yt-transcript`), Flow 2
(`yt-meta`), or any of the others. Absolute upload date is **not** in
the result file (YouTube only exposes relative dates — "2 weeks ago" —
on the search results page, and `--flat-playlist` skips the per-video
round-trip); fetch `yt-meta` on the chosen URL if you need it.

> Files land in `yt-cache/_search/<slug>-<unix-ns>.md` (outside any
> `<video-id>/`) — the nanosecond timestamp guarantees re-running the
> same query never overwrites the previous run, even in the same second.
> YouTube's search ranking is not stable between calls; treat the file
> as a snapshot, not a cache.

### Flow 1 — transcript-driven frames

```bash
# 1) get the transcript; agent reads markdown and notes timestamps
yt-transcript https://www.youtube.com/watch?v=dQw4w9WgXcQ
# → ./yt-cache/dQw4w9WgXcQ/transcript.md

# 2) pull only the frames you actually need
yt-frames https://www.youtube.com/watch?v=dQw4w9WgXcQ --timestamps 0:43,1:23,2:30
# Wrote: ./yt-cache/dQw4w9WgXcQ/frames/frame_0043.jpg
# Wrote: ./yt-cache/dQw4w9WgXcQ/frames/frame_0123.jpg
# Wrote: ./yt-cache/dQw4w9WgXcQ/frames/frame_0230.jpg
```

### Flow 2 — video metadata

```bash
# Description, chapters, most-replayed, counts, tags — one markdown file.
# Free: same yt-dlp --dump-json the transcript path already runs.
yt-meta https://www.youtube.com/watch?v=dQw4w9WgXcQ
# → ./yt-cache/dQw4w9WgXcQ/meta.md
```

The chapter and most-replayed anchors are `[mm:ss]`, so they paste straight
into `yt-frames --timestamps` / `yt-listen --timestamps`.

### Flow 3 — comments

```bash
# Top 50 comments (with replies) as markdown. Separate paginated scrape —
# slower than the others; bump the cap only when you need it.
yt-comments https://www.youtube.com/watch?v=dQw4w9WgXcQ
# → ./yt-cache/dQw4w9WgXcQ/comments.md

yt-comments URL --max 200          # pull more (slower)
yt-comments URL --sort new         # newest-first instead of top
```

> **Cost note:** comments are *not* part of `yt-meta` and are *not* free —
> each run paginates YouTube's comment feed and can take minutes on viral
> videos. Invoke it only when comments are actually what you need.

### Flow 4 — audio FFT analysis at specific moments

```bash
# Per timestamp: clip.wav + spectrum.png + features.md (BPM, key, chord, MFCC, etc.)
yt-listen https://www.youtube.com/watch?v=dQw4w9WgXcQ --timestamps 0:30 --duration 8s
# Wrote: ./yt-cache/dQw4w9WgXcQ/audio/clip_0030.wav
# Wrote: ./yt-cache/dQw4w9WgXcQ/audio/spectrum_0030.png
# Wrote: ./yt-cache/dQw4w9WgXcQ/audio/features_0030.md
```

### Flow 5 — scene-driven bulk frames

```bash
yt-frames URL --mode scene --scene-threshold 27
# Or combined transcript + scene-frames in one self-contained .md:
yt-watch URL
```

### Flow F — OCR (silent-with-text videos)

When `yt-transcript` returns 0 bytes (or near-nothing) and the content
lives entirely in burned-in overlay text — tutorial channels with
schematic labels, chord matrices over dimmed B-roll, parameter
walkthroughs without voice-over — fall back to OCR over cached frames.
Engine is [RapidOCR](https://github.com/RapidAI/RapidOCR) (PP-OCRv5
models via `onnxruntime`).

```bash
# 1) extract frames first (lower scene threshold catches overlay fades
#    within the same shot; or use --mode interval for a denser sample)
yt-frames URL --mode scene --scene-threshold 12
# or:
yt-frames URL --mode interval --interval 15s

# 2) OCR every cached frame → markdown with [mm:ss] anchors
yt-ocr URL
# → ./yt-cache/<vid>/ocr.md

# Or skip step 1 — let yt-ocr extract on its own:
yt-ocr URL --timestamps 1:30,2:45,5:10

# Non-English overlays:
yt-ocr URL --language ru        # Cyrillic
yt-ocr URL --language ja        # Japanese
yt-ocr URL --language zh        # Chinese (simplified)
yt-ocr URL --language multi     # PP-OCR multilingual (Chinese+English)
```

The result file mirrors `transcript.md`: per-`[mm:ss]` block, one line
per detected text region, an explicit `_(no text detected)_` marker for
frames where the engine returned nothing (so an agent can tell the frame
was checked vs. silently omitted).

> **Install the `[ocr]` extra.** RapidOCR and `onnxruntime` are **not**
> in the core install. If `yt-ocr` exits with the missing-extra hint,
> run:
> ```bash
> pipx inject yt-tools rapidocr onnxruntime
> # or for non-pipx setups:
> pip install 'yt-tools[ocr]'
> ```
> First run with a given `--language` lazy-downloads a ~10 MB PP-OCRv5
> ONNX model into `~/.cache/rapidocr/`.

### Cache hygiene

```bash
yt-tools cache list                      # show cached source-mp4 sizes
yt-tools cache prune --older-than 7d     # drop sources older than a week
```

## Output layout

Per video, all artefacts land under `./yt-cache/<video-id>/` in the current
working directory; the one exception is `yt-search`, which writes to
`./yt-cache/_search/` because its output isn't tied to a single video:

```
./yt-cache/
  _search/
    <slug>-<unix>.md       # yt-search output (one per query invocation)
  <video-id>/
    source.mp4             # cached source (≤720p, reused by yt-frames / yt-listen / yt-watch)
    transcript.md          # yt-transcript output
    meta.md                # yt-meta output
    comments.md            # yt-comments output
    ocr.md                 # yt-ocr output (re-reads frames/ — same dir as yt-frames)
    watch.md               # yt-watch output
    frames/
      frame_<mmss>.jpg     # yt-frames / yt-watch (zero-padded mmss)
    audio/
      clip_<mmss>.wav      # yt-listen per-timestamp clip
      spectrum_<mmss>.png  # yt-listen mel-spectrogram
      features_<mmss>.md   # yt-listen feature report (BPM / key / chord / MFCC / spectral stats)
```

The last line of stdout (or one line per artefact for multi-output commands
like `yt-frames` and `yt-listen`) is the absolute path of the produced file,
prefixed with `Wrote: `. This makes piping into agent tooling or shell
scripts trivial.

## Defaults

- **Cache directory:** `./yt-cache/<video-id>/` in cwd (`.gitignore`-friendly).
- **Source caching:** on by default (`--no-cache-source` to stream via
  `yt-dlp -g | ffmpeg`).
- **Combined embed (`yt-watch`):** sidecar `![](frames/frame_<mmss>.jpg)`,
  never base64 (avoids ~33 % token bloat).
- **Distill (`yt-transcript --distill`):** prints a hint to invoke an external
  distillation step (`mcp__interns__transcript_distill` in Claude Code); the
  CLI itself never calls an LLM.
- **Scene threshold:** 27 (PySceneDetect `ContentDetector` default; lower =
  more sensitive).
- **`yt-listen` defaults:** 8-second clip per timestamp, mel-spectrogram at
  default `librosa` settings, full feature set when `[full]` extra is
  installed.

## Requirements

- Python ≥ 3.10, < 3.13 (`librosa` Py 3.13 friction holds the ceiling)
- `ffmpeg` on PATH (external binary, see Installation)
- `pipx` recommended for install (any pip-compatible installer works)

## Design choices

**No MCP wrapper.** Each CLI is a stateless one-shot transform: URL → artefact.
There is no typed schema discovery, no shared cache across sessions, no
persistent connection an MCP server would benefit from. `Bash` is the right
caller.

**No Whisper / Gemini for transcription.** `yt-transcript` uses YouTube's
`auto-sub` via `youtube-transcript-api`. Whisper would add a massive runtime
dep for a marginally cleaner transcript; the iterative flow tolerates auto-sub
quality and benefits more from `--distill` on the markdown than from a heavier
STT step.

**Iterative > bulk.** The primary flow is "transcript first, then targeted
heavy fetches". Scene-mode and interval-mode are secondary, opt-in via flags.

## Development

```bash
git clone https://github.com/kzntsv-dev/yt-tools.git
cd yt-tools
pip install -e ".[full,test]"
pytest tests/
```

Test layer covers pure logic (video-id extraction, mm:ss conversions,
snippets → markdown rendering, cache list/prune, interleaved rendering,
subprocess failure formatting) and CLI smoke (transcript / frames / listen /
watch end-to-end with mocked subprocess calls). YouTube + `yt-dlp` + `ffmpeg`
are mocked at the smoke layer — no network is touched.

## License

MIT — see [LICENSE](LICENSE).
