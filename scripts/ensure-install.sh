#!/usr/bin/env bash
# yt-tools plugin — SessionStart hook (POSIX / bash).
#
# Idempotent ensure-install: on every session start, verify that the
# yt-tools package is installed via pipx from this plugin's clone (the
# $CLAUDE_PLUGIN_ROOT directory) at the version declared in the clone's
# pyproject.toml, and that ffmpeg is on PATH. Print per-OS install hints
# when something is missing; never block session start (always exit 0,
# errors go to stderr).
#
# Windows users: if this hook fails to execute (e.g. no bash on PATH),
# run the PowerShell equivalent manually:
#   pwsh -File "$CLAUDE_PLUGIN_ROOT/scripts/ensure-install.ps1"

set -u

log() { printf '[yt-tools] %s\n' "$*" >&2; }

# 0. Resolve plugin root ───────────────────────────────────────────────────
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$PLUGIN_ROOT" ]; then
    log "CLAUDE_PLUGIN_ROOT not set — running outside plugin context; skipping."
    exit 0
fi
if [ ! -f "$PLUGIN_ROOT/pyproject.toml" ]; then
    log "Missing pyproject.toml at $PLUGIN_ROOT — plugin layout broken; skipping."
    exit 0
fi

# Parse declared version from the plugin's pyproject.toml (line: version = "X.Y.Z")
declared_version=$(awk -F'"' '/^version = / { print $2; exit }' "$PLUGIN_ROOT/pyproject.toml")
if [ -z "$declared_version" ]; then
    log "Could not parse version from $PLUGIN_ROOT/pyproject.toml; skipping."
    exit 0
fi

# 1. Probe pipx ────────────────────────────────────────────────────────────
if ! command -v pipx >/dev/null 2>&1; then
    log "pipx not found on PATH. Install it first:"
    log "  python -m pip install --user pipx"
    log "  python -m pipx ensurepath   # restart shell after"
    log "Then this hook will install yt-tools on the next session start."
    exit 0
fi

# 2. Probe yt-tools — install or update from plugin clone ──────────────────
installed_version=""
if pipx list --short 2>/dev/null | grep -q '^yt-tools '; then
    installed_version=$(pipx list --short 2>/dev/null | awk '/^yt-tools / {print $2}')
fi

needs_install=true
if [ -n "$installed_version" ] && [ "$installed_version" = "$declared_version" ]; then
    needs_install=false
    log "yt-tools $installed_version installed from plugin clone — ok"
fi

if [ "$needs_install" = "true" ]; then
    if [ -n "$installed_version" ]; then
        log "Installed $installed_version != plugin $declared_version; reinstalling from $PLUGIN_ROOT..."
    else
        log "yt-tools not installed; installing from $PLUGIN_ROOT via pipx..."
    fi
    # --force allows reinstall over existing; installs from the plugin clone
    # itself (not from PyPI). For chord-progression / structure features, the
    # user can later run:
    #   pipx inject yt-tools "bpm-detector @ git+https://github.com/libraz/bpm-detector@v1.1.0"
    if ! pipx install --force "$PLUGIN_ROOT" >&2; then
        log "WARN: pipx install from $PLUGIN_ROOT failed. Investigate pipx state."
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
