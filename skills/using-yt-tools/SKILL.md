---
name: using-yt-tools
version: 0.3.0
description: Three flows for YouTube content. **Iterative-watch** (summary / exploration) — transcript with [mm:ss] anchors → pick moments → extract frames. **Targeted-frames** (specific timestamps) — extract frames directly, no transcript. **Audio-analysis** (music FFT) — per timestamp spectrogram + numeric digest (BPM, key, chord progression, harmonic content) via `yt-listen`. Triggers (mixed RU/EN — same skill serves both audiences) — "what's in this video", "video summary", "youtube transcript", "что в ролике", "о чём видео", "show frame at N", "покажи кадр на N", "listen to fragment at N", "послушай момент N", "what's the BPM", "BPM/тональность видео", "analyze audio", "спектрограмма", or any youtube.com URL. CLI installed via `pipx install yt-tools` (from PyPI; the bundled plugin SessionStart hook auto-installs it). YouTube-only — for Vimeo / Twitch / local files use other tools.
---

# using-yt-tools

Iterative YouTube watching for an agent — clean-markdown transcript with
`[mm:ss]` anchors → the agent decides which moments are interesting →
targeted frame extraction at those timestamps → the agent reads the frames
via its vision tool. An alternative flow — if the user has already named
the timestamps, go straight to frames without the transcript. For musical
URLs there is a third flow with FFT analysis (BPM, key, chord progression,
spectrum) via `yt-listen`.

## When to use

Three distinct flows, picked by user intent:

**Flow A — iterative-watch** (exploration / summary):

- The user asks what's in the video, wants a summary, wants to know what the
  video is about.
- Steps: fetch transcript → read → pick interesting moments → extract those
  frames → Read frames.
- Trigger phrases: "what's in this video", "video summary", "youtube
  transcript", "watch this video", «что в этом ролике», «о чём ролик»,
  «расшифровка YouTube».

**Flow B — targeted-frames** (specific moments):

- The user has already named concrete timestamps; a transcript is extra
  work.
- Steps: extract frames at the given timestamps → Read frames.
- Trigger phrases: "show frame at N", "look at moment N", "what's shown at
  N", «покажи кадр на N», «посмотри момент N», «что показано на N».

**Flow C — audio-analysis** (music FFT):

- The user asks for a music breakdown — BPM, key, harmony, chord
  progression, spectrum, harmonic content.
- Steps: `yt-listen URL --timestamps T1,T2,...` → per timestamp three
  artefacts (`clip.wav` + `spectrum.png` + `features.md`) → Read **both**
  (the PNG via vision + the .md for the numbers).
- Trigger phrases: "listen to fragment at N", "what's the BPM", "harmony",
  "analyze audio", «послушай момент N в <URL>», «какой BPM», «тональность
  видео», «гармония», «спектрограмма», «что в музыке на T».
- If the video has captions, `yt-transcript` is optional context — but
  **not** for lyrics-from-music (see What NOT to do).

All three flows assume the `yt-tools` CLI is installed. When this skill
ships as part of the `yt-tools` Claude Code plugin, the `SessionStart`
hook runs `pipx install yt-tools` automatically on the first session after
plugin install. When the skill is used standalone, the user must run
`pipx install yt-tools` themselves (see Prerequisites → Installing the
CLI). Binaries may or may not be on the current session's PATH — that's
normal, especially right after a fresh `winget install` or `pipx
ensurepath` (PATH is per-shell, not picked up by the *current* shell).
**Never abort on a bare `Get-Command yt-frames` / `command -v yt-frames`
miss** — first run the resolve chain (see Prerequisites → Locating
binaries).

## Prerequisites

### Installing the CLI

Two install paths, both equivalent for skill behaviour:

1. **Via this plugin (recommended for Claude Code users).** Install the
   plugin once — `/plugin install yt-tools@opeitcloc03-claude-plugins` —
   and the SessionStart hook runs `pipx install --force "$CLAUDE_PLUGIN_ROOT"`
   on the next session, installing yt-tools directly from the plugin's
   local clone (no PyPI involvement). See the plugin README for marketplace
   setup.
2. **Standalone (any environment).** Install directly from the Git repo
   via pipx:
   ```bash
   pipx install git+https://github.com/OpeItcLoc03/yt-tools.git
   ```
   For chord progression + structural analysis features in `yt-listen`,
   use the `[full]` extra:
   ```bash
   pipx install "git+https://github.com/OpeItcLoc03/yt-tools.git#egg=yt-tools[full]"
   ```

External binary that is **not** pip-installable in either case:

- **ffmpeg** — required for source video caching and per-clip extraction.
  Per-OS install: `winget install Gyan.FFmpeg` (Windows), `brew install
  ffmpeg` (macOS), `sudo apt install ffmpeg` (Debian/Ubuntu),
  `sudo dnf install ffmpeg` (Fedora/RHEL).

### Locating binaries

This skill makes no assumption about an active PATH. **Step 0 of every
flow** is to resolve the paths for `yt-frames` / `yt-transcript` /
`yt-listen` and `ffmpeg` (`yt-dlp` ships in the same pipx venv). If you
resolve through a fallback path, use PATH-prepend on each invocation (see
Invoke pattern below). Abort **only** if the binary is not on PATH and
not in any of the known install locations.

**yt-tools CLI** (any single location gives all five binaries —
`yt-frames`, `yt-transcript`, `yt-listen`, `yt-watch`, `yt-tools` — plus
a shimmed `yt-dlp`):

1. **PATH**: `Get-Command yt-frames` (pwsh) / `command -v yt-frames`
   (bash). For Flow C also probe `yt-listen` (present from pyproject
   `0.2.0+`; if only `yt-frames` is found and `yt-listen` is missing, the
   machine is on an old `0.1.x` install — run `pipx reinstall yt-tools`
   or `pipx upgrade yt-tools`).
2. **pipx-shim direct path** (when PATH is stale after a fresh `pipx
   ensurepath`):
   - Windows: `~/.local/bin/yt-frames.exe` (plus `yt-listen.exe`)
   - Linux/macOS: `~/.local/bin/yt-frames` (plus `yt-listen`)
3. **If neither location resolves** — install hint, then stop. **Do not
   recreate any legacy `.venv/`** even if you find one on disk: the
   current install path is pipx-only, and a stale project-local venv is
   leftover from a pre-distribution layout and should not be used or
   regenerated. Install hint:
   ```
   python -m pip install --user pipx
   python -m pipx ensurepath                                       # one-time; restart shell after
   pipx install git+https://github.com/OpeItcLoc03/yt-tools.git    # core
   # For chord progression / structure analysis (optional):
   # pipx install "git+https://github.com/OpeItcLoc03/yt-tools.git#egg=yt-tools[full]"
   ```
   If you are inside Claude Code, prefer the plugin path instead — install
   `yt-tools@opeitcloc03-claude-plugins` and the bundled SessionStart hook
   does the pipx install from the plugin's local clone automatically.

**ffmpeg**:

1. PATH: `Get-Command ffmpeg` / `command -v ffmpeg`.
2. Windows winget cache (the path version floats, so glob it):
   `~/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_*/ffmpeg-*-full_build/bin/ffmpeg.exe`
3. macOS Homebrew: `/opt/homebrew/bin/ffmpeg` (Apple Silicon) or
   `/usr/local/bin/ffmpeg` (Intel).
4. Linux: `/usr/bin/ffmpeg` (apt) or `/usr/local/bin/ffmpeg`.
5. If no location resolves — print the per-OS install hint
   (`winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install
   ffmpeg`) and stop. **Do not** ask the user to restart Claude Code —
   continue the resolve logic in the same session once ffmpeg is
   installed, or note that the next CC session will pick it up on PATH
   refresh.

### Invoke pattern

`yt-frames` spawns `yt-dlp` and `ffmpeg` as child processes via
`subprocess.run([..., "ffmpeg", ...])`, so a full path to `yt-frames.exe`
alone is **not enough** — you need a PATH-prepend so the child processes
also see them.

Substitute `$YTBIN` with the directory where you resolved `yt-frames` in
the probe step (typically `~/.local/bin/` for the pipx-shim layout).

```bash
# bash / git-bash — after resolving through a fallback
FFDIR=$(dirname "$(ls ~/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_*/ffmpeg-*-full_build/bin/ffmpeg.exe 2>/dev/null | head -1)")
YTBIN=~/.local/bin
PATH="$FFDIR:$YTBIN:$PATH" yt-frames <url> --timestamps 1:23,4:56
```

```powershell
# pwsh — glob over the floating ffmpeg version
$ff = (Get-ChildItem "$HOME\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*-full_build\bin\ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).DirectoryName
$ytbin = "$HOME\.local\bin"
$env:PATH = "$ff;$ytbin;" + $env:PATH
yt-frames <url> --timestamps 1:23,4:56
```

If both resolved directly on PATH (`Get-Command` returned something), no
prepend is needed — invoke normally.

## Inputs

| Flow | Required | Optional |
|---|---|---|
| A — iterative-watch | YouTube URL or bare 11-char video id | `--lang ru,en` for non-English subs; `--out PATH` |
| B — targeted-frames | YouTube URL + timestamps (`mm:ss`, `h:mm:ss`, or bare seconds: `123` → 2:03) | `--no-cache-source` (stream instead of caching `source.mp4`); `--out DIR` |
| C — audio-analysis | YouTube URL + timestamps (same formats as B) | `--duration 30s` (default 30s — the lower bound for beat-tracking); `--mode interval --interval 60s` (bulk sampling); `--no-wav` / `--no-spectrogram` (both default ON); `--linear` (STFT instead of mel); `--chroma` (bonus chromagram PNG); `--sample-rate 22050`; `--no-cache-source`; `--out DIR` |

All three flows write to `<cwd>/yt-cache/<video-id>/` by default (Flow C
into the `audio/` sub-directory).

## Steps

### Flow A — iterative-watch

```
0. Resolve yt-frames + ffmpeg per Prerequisites → Locating binaries; build PATH-prepend if resolved via fallback
1. yt-transcript <url>                        → ./yt-cache/<vid>/transcript.md
2. Read transcript.md, find [mm:ss] anchors that match the question
3. yt-frames <url> --timestamps 1:23,4:56,…   → ./yt-cache/<vid>/frames/frame_*.jpg
4. Read each frame_*.jpg via the vision tool
5. Answer the user, citing both transcript paragraph and frame contents
```

**Stdout contract per CLI** (take the last line; format depends on the
CLI):

- `yt-transcript`, `yt-watch` — one stdout line: the bare absolute path of
  the artefact (`<abs>/transcript.md` or `<abs>/watch.md`).
- `yt-frames` — **N lines** of the form `Wrote: <abs path>`, one per
  extracted frame. Strip the `"Wrote: "` prefix to get each path. This is
  deliberate per-line output so callers can pipe / scrape without parsing
  a summary line.

Warnings and errors go to stderr (`warning: …`, `error: …`); stdout stays
machine-parseable.

### Flow B — targeted-frames

```
0. Resolve yt-frames + ffmpeg per Prerequisites → Locating binaries; build PATH-prepend if resolved via fallback
1. Parse the user's timestamps (mm:ss / h:mm:ss / bare seconds — all accepted)
2. yt-frames <url> --timestamps 1:23,4:56,…   → ./yt-cache/<vid>/frames/frame_*.jpg
3. Read each frame_*.jpg
4. Answer the user, referencing each frame by its [mm:ss] label
```

No transcript fetch. If the user later asks "what was said at that
moment?", switch to Flow A on the same URL — the `source.mp4` cache is
reused, so there is no re-download.

### Flow C — audio-analysis

```
0. Resolve yt-listen + ffmpeg per Prerequisites → Locating binaries; build PATH-prepend if resolved via fallback
1. Parse timestamps (mm:ss / h:mm:ss / bare seconds — same as Flow B)
2. yt-listen <url> --timestamps T1,T2,...    → ./yt-cache/<vid>/audio/{clip,spectrum,features}_TTTT.{wav,png,md}
3. Read **both** per timestamp: features_TTTT.md (numbers — BPM, key, chord progression, spectral features, peak frequencies, harmonic/percussive split) + spectrum_TTTT.png (vision)
4. Reason about BPM / key / chord / spectral. Cite the concrete numbers from features.md; the spectrum PNG is a supplementary signal, not the primary one (see What NOT to do).
```

The `yt-listen` stdout contract is one `Wrote: <abs path>` line per
artefact (three per timestamp — wav, png, md), same as `yt-frames`.

The `source.mp4` cache is shared between Flows A / B / C on the same URL
— no repeated downloads. Default duration is 30s (the lower bound for
beat-tracking); `--duration` overrides it. For bulk-sampling a musical
video, use `--mode interval --interval 60s` instead of explicit
timestamps.

## Failure modes

All failures abort cleanly; never leave a half-finished state.

| Symptom | Cause | Action |
|---|---|---|
| `yt-transcript` / `yt-frames` not on PATH | yt-tools is installed but the session's PATH does not include the pipx-shim directory | Run the **full** probe chain (PATH → `~/.local/bin/`). Abort and print the install hint **only** if neither location yielded anything. **Do not** reinstall yt-tools when a pipx-shim exists — it's a PATH problem, not a missing package (see What NOT to do). |
| `yt-dlp not found on PATH` (from a child process) | `yt-dlp` lives in the same pipx venv as `yt-frames`, but the PATH-prepend was not built | Re-build the PATH-prepend (Prerequisites → Invoke pattern) — point `$YTBIN` at the directory where you found `yt-frames`. |
| `ffmpeg not found on PATH` (from a child process) | ffmpeg is installed but only in the winget cache / Homebrew prefix / etc., not on the session's PATH | Run the ffmpeg resolve per Prerequisites and PATH-prepend. Abort only if no location yielded the binary — then print the per-OS install hint. **Do not** require the user to restart the Claude Code session — the resolve handles it. |
| `yt-dlp source download failed (exit N) \| stderr: …` | Network failure / private / age-gated / region-locked / malformed URL | Print the captured stderr verbatim; do not retry. |
| `yt-dlp --dump-json failed` | Same, but on the metadata step | Same. |
| `Subtitles disabled` from `youtube-transcript-api` | The channel disabled captions | Fatal for Flow A — tell the user, suggest Flow B with explicit timestamps if appropriate. |
| User passed a non-YouTube URL (Vimeo / Twitch / local mp4) | Out of scope | Stop; say the skill is YouTube-only. |

## Side effects

- Writes under `<cwd>/yt-cache/<video-id>/`:
  - `transcript.md` (Flow A)
  - `source.mp4` (≤ 720p; produced by either flow unless `--no-cache-source`)
  - `frames/frame_<mmss>.jpg` per extracted frame
  - `audio/{clip,spectrum,features}_<mmss>.{wav,png,md}` (Flow C)
- Network: `yt-dlp` pulls metadata + optionally `source.mp4`;
  `youtube-transcript-api` pulls subs.
- No external state is mutated — pure local-fs side effects.
- `source.mp4` may be ~50–200 MB per 720p / 10-minute video; the cache is
  reused between calls. **Warning** — it accumulates: 20 videos ≈ 1–4 GB
  on disk.

Cache hygiene: `yt-tools cache list` shows usage, `yt-tools cache prune
--older-than 7d` clears the old ones.

## What NOT to do

- **Don't recreate a deleted venv from the install hint.** If you find a
  stale `lib/yt-tools/.venv/` somewhere on disk, do not regenerate it —
  the current install path is pipx-only. Check `~/.local/bin/yt-frames`
  first. An empty `.venv/` ≠ "yt-tools is not installed": the machine
  has migrated to pipx and the old venv is legacy. Recreating a venv on
  top of a working pipx install is a destructive cleanup paradox (wastes
  ~200 MB and creates two parallel installs). If the pipx-shim exists but
  `Get-Command yt-frames` is empty, the fix is `pipx ensurepath` +
  restart shell, not a new venv.
- **Don't run Flow A when the user has already named timestamps.** "Look
  at 1:23 and 4:56" → go straight to Flow B. Fetching the transcript
  first is pure waste.
- **Don't bulk-extract "just in case".** Flow A takes frames from the
  transcript, Flow B from explicit user input. Never `--mode interval
  --interval 5s` "to be safe".
- **Don't use `yt-watch` as the default Flow A renderer.** `yt-watch`
  combines transcript + scene-frames into a single document — heavier
  (requires an ffmpeg scene-detect pass over `source.mp4`). Use it only
  when the user wants one self-contained document.
- **Don't shell-quote URLs as a single command string.** Use the CLI
  list-form (already list-form in `subprocess.run`); YouTube URLs contain
  `?` and `&`, which break naive quoting.
- **Don't retry on `yt-dlp` failures.** A failure here means the video is
  genuinely unavailable (private / region / age) or the user's auth is
  broken. Retries waste tokens.
- **Don't paraphrase / translate the transcript silently in your answer.**
  The artefact is for your reasoning; cite it with `[mm:ss]` anchors when
  you quote a passage.
- **Don't invoke the skill on non-YouTube URLs.** Vimeo / Twitch / TikTok
  / local mp4 — out of scope. Use other tools (or `yt-dlp` directly).
- **Don't write results to arbitrary paths.** Default is
  `<cwd>/yt-cache/<vid>/`; pass `--out` only if the user explicitly asked
  for it.
- **Don't run Whisper on mixed music.** If the user asks for lyrics from
  a musical clip — this is **not** `yt-listen`'s job. Whisper on mixed
  music without source separation is garbage (confirmed in arXiv
  2506.15514). Tell the user that lyrics-from-music is a separate
  pipeline (Demucs / Spleeter source-separation + Whisper over the
  isolated vocals), out of scope for the current `yt-tools`. Don't try to
  substitute `yt-transcript` either — YouTube auto-subs for music are
  usually absent, and `yt-listen` has no Whisper flag even as an option.
- **Don't interpret `spectrum_*.png` without `features_*.md` in the same
  pair.** VLM signal on audio spectrograms is limited (~50–60 %
  accuracy on ESC-10 vs 72.5 % human; Dixit et al. arXiv 2411.12058). The
  numeric digest from `features.md` is the primary channel; the spectrum
  PNG is a supplementary visual cue. When you read the PNG, always read
  the `.md` for the same timestamp; cite BPM / key / chord / spectral
  values from the textual fields, not from "what the picture looks
  like".
