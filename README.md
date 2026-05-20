# yt-tools

CLI wrap for **iterative agent-driven YouTube watching**. The agent reads the
transcript, decides which moments matter, then pulls only those frames — no
bulk download, no JSON soup, no MCP scaffolding.

## Primary flow

```
yt-transcript URL                         → ./yt-cache/<vid>/transcript.md
agent reads markdown, picks [mm:ss] anchors
yt-frames URL --timestamps 1:23,4:56      → ./yt-cache/<vid>/frames/frame_0123.jpg
agent Read's each frame_*.jpg via its vision tool
```

Last line of each CLI's stdout is the absolute path of the artefact (or one
line per frame for `yt-frames`) so the caller never has to guess.

## CLIs

| CLI | What it does |
|---|---|
| `yt-transcript URL [--out PATH] [--lang ru,en] [--distill]` | Clean markdown transcript with metadata header + `[mm:ss]` paragraph anchors copy-paste-friendly for `--timestamps`. |
| `yt-frames URL [--out DIR] [--timestamps 1:23,4:56] [--mode interval --interval 30s] [--mode scene --scene-threshold N] [--no-cache-source]` | Targeted frame extraction. Default mode = timestamps. |
| `yt-watch URL [--out DIR] [--scene-threshold N]` | Secondary: combined transcript + scene-frames in one `.md` with `![](frames/...)` sidecar embed. |
| `yt-tools cache list \| prune [--older-than 7d]` | Manage the source-mp4 cache. |

## Source-mp4 cache

The first `yt-frames` call for a URL downloads `source.mp4` (≤720p) into
`./yt-cache/<vid>/`. Subsequent calls reuse it via `ffmpeg -ss` (instant, no
re-download). Pass `--no-cache-source` to stream the source through
`yt-dlp -g | ffmpeg` instead — no mp4 written to disk.

Layout per video:

```
./yt-cache/<vid>/
  source.mp4           ← cached source (only with default cache mode)
  transcript.md        ← yt-transcript output
  watch.md             ← yt-watch output
  frames/
    frame_0123.jpg     ← yt-frames / yt-watch outputs (mmss zero-padded)
```

## Install

Lives in `~/projects/.common/lib/yt-tools/`. Install editable into a venv:

```powershell
cd ~/projects/.common/lib/yt-tools
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

External binaries required on PATH (not pip-installed):

- **yt-dlp** — `winget install yt-dlp.yt-dlp` / `brew install yt-dlp` / `pip install -U yt-dlp`
- **ffmpeg** — `winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg`

Verify entry-points (after `pip install -e .`):

```powershell
yt-transcript --help
yt-frames --help
yt-watch --help
yt-tools cache --help
```

## Usage

### Iterative agent flow

```powershell
# 1) transcript first — agent reads the markdown
yt-transcript https://www.youtube.com/watch?v=dQw4w9WgXcQ
# → C:\...\yt-cache\dQw4w9WgXcQ\transcript.md

# 2) targeted frames from the timestamps the agent spotted in the transcript
yt-frames https://www.youtube.com/watch?v=dQw4w9WgXcQ --timestamps 0:43,1:23,2:30
# Wrote: C:\...\frame_0043.jpg
# Wrote: C:\...\frame_0123.jpg
# Wrote: C:\...\frame_0230.jpg

# 3) agent calls its Read tool on each .jpg → visual answer
```

### Bulk-scene mode (secondary)

```powershell
yt-frames URL --mode scene --scene-threshold 27
yt-watch URL                  # combined transcript + scene-frames in one .md
```

### Interval mode

```powershell
yt-frames URL --mode interval --interval 30s
```

### Cache hygiene

```powershell
yt-tools cache list
yt-tools cache prune --older-than 7d
```

## Defaults

- **Artifacts:** `./yt-cache/<video-id>/` in cwd
- **Combined embed (`yt-watch`):** sidecar `![](frames/frame_<mmss>.jpg)`, never base64
- **Distill:** `--distill` only prints a hint to invoke `mcp__interns__transcript_distill` on the artefact; the CLI itself never calls an LLM
- **Scene threshold:** 27 (PySceneDetect `ContentDetector` default; lower = more sensitive)
- **Source caching:** on by default; `--no-cache-source` to stream

## Tests

```powershell
cd ~/projects/.common/lib/yt-tools
python -m pytest tests/
```

67 tests cover the pure logic (video-id extraction, mm:ss conversions,
snippets → markdown rendering, cache list/prune, interleaved `yt-watch`
rendering) and CLI smoke (yt-transcript, yt-frames timestamps/interval modes,
yt-tools cache). YouTube + yt-dlp + ffmpeg are mocked in the smoke layer — no
network is touched. E2E on a real URL lives in the `claude-skills` repo
(`using-yt-tools-test-trigger`).

## Why not MCP

Stateless one-shot transforms (URL → artefact). Each CLI is a thin wrapper
around `youtube-transcript-api` + `yt-dlp` + `ffmpeg` + `PySceneDetect`. No
shared cache across sessions, no typed schema discovery the agent would
benefit from, no persistent connection. `Bash` is the right caller. Add an
MCP wrapper later only if cross-project video metadata caching becomes a
real need.

## Why not Whisper / Gemini for transcription

We use YouTube's `auto-sub` via `youtube-transcript-api`. Whisper would add a
massive runtime dep and produce a slightly cleaner transcript at the cost of
seconds-to-minutes per video. The agent flow tolerates auto-sub quality and
benefits more from `--distill` on the markdown (cheap intern LLM) than from a
heavier STT step.

## Design source

`~/projects/.workshop/.archive/2026-05-20-yt-tools.md` — full design trace
including GitHub research that justified building over reuse (existing MCP
wrappers return raw `youtube-transcript-api` shape; `youtube-screenshot-extractor`
requires Deno; combined-tools output JSON / wikis instead of one `.md`).
