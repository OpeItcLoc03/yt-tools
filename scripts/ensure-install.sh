#!/usr/bin/env bash
# yt-tools plugin — SessionStart hook (POSIX / bash).
#
# Idempotent ensure-install: on every session start, verify that the
# yt-tools PyPI package is installed via pipx at >= PLUGIN_VERSION, and
# that ffmpeg is on PATH. Print per-OS install hints when something is
# missing; never block session start (always exit 0, errors go to stderr).
#
# Windows users: if this hook fails to execute (e.g. no bash on PATH),
# run the PowerShell equivalent manually:
#   pwsh -File "$CLAUDE_PLUGIN_ROOT/scripts/ensure-install.ps1"

set -u

PLUGIN_VERSION="0.3.0"

log() { printf '[yt-tools] %s\n' "$*" >&2; }

# 1. Probe pipx ────────────────────────────────────────────────────────────
if ! command -v pipx >/dev/null 2>&1; then
    log "pipx not found on PATH. Install it first:"
    log "  python -m pip install --user pipx"
    log "  python -m pipx ensurepath   # restart shell after"
    log "Then this hook will install yt-tools on the next session start."
    exit 0
fi

# 2. Probe yt-tools — check installed version via pipx ─────────────────────
installed_version=""
if pipx list --short 2>/dev/null | grep -q '^yt-tools '; then
    installed_version=$(pipx list --short 2>/dev/null | awk '/^yt-tools / {print $2}')
fi

needs_install=true
if [ -n "$installed_version" ]; then
    # If installed >= required (lexical-sorted semver works for x.y.z), skip.
    highest=$(printf '%s\n%s\n' "$installed_version" "$PLUGIN_VERSION" | sort -V | tail -1)
    if [ "$highest" = "$installed_version" ]; then
        needs_install=false
        log "yt-tools $installed_version installed (>= plugin $PLUGIN_VERSION) — ok"
    fi
fi

if [ "$needs_install" = "true" ]; then
    if [ -n "$installed_version" ]; then
        log "yt-tools $installed_version < $PLUGIN_VERSION; upgrading via pipx..."
        if ! pipx upgrade yt-tools >&2; then
            log "WARN: pipx upgrade yt-tools failed. Investigate manually."
        fi
    else
        log "yt-tools not installed; installing via pipx..."
        if ! pipx install yt-tools >&2; then
            log "WARN: pipx install yt-tools failed. Check PyPI access and pipx state."
        fi
    fi
fi

# 3. Probe ffmpeg ──────────────────────────────────────────────────────────
if ! command -v ffmpeg >/dev/null 2>&1; then
    case "$(uname -s 2>/dev/null || echo unknown)" in
        Darwin*)
            log "ffmpeg not on PATH. Install via Homebrew:  brew install ffmpeg"
            ;;
        Linux*)
            log "ffmpeg not on PATH. Install via your package manager:"
            log "  Debian/Ubuntu:  sudo apt install ffmpeg"
            log "  Fedora/RHEL:    sudo dnf install ffmpeg"
            log "  Arch:           sudo pacman -S ffmpeg"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            log "ffmpeg not on PATH (Windows). Install via winget:"
            log "  winget install Gyan.FFmpeg"
            log "Then restart the shell so the new PATH is picked up."
            ;;
        *)
            log "ffmpeg not on PATH. Install via your platform's package manager."
            ;;
    esac
fi

exit 0
