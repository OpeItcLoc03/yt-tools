# yt-tools plugin — SessionStart hook (PowerShell variant for Windows).
#
# Idempotent ensure-install: on every session start, verify that the
# yt-tools package is installed via pipx from this plugin's clone (the
# $env:CLAUDE_PLUGIN_ROOT directory) at the version declared in the clone's
# pyproject.toml, and that ffmpeg is on PATH. Print install hints when
# something is missing; never block session start (always exit 0, errors go
# to stderr).
#
# Invoked manually on Windows if hooks.json's POSIX command does not run:
#   pwsh -File "$env:CLAUDE_PLUGIN_ROOT/scripts/ensure-install.ps1"

$ErrorActionPreference = 'Continue'

function Write-PluginLog {
    param([string]$Message)
    [Console]::Error.WriteLine("[yt-tools] $Message")
}

# 0. Resolve plugin root ───────────────────────────────────────────────────
$PluginRoot = $env:CLAUDE_PLUGIN_ROOT
if (-not $PluginRoot) {
    Write-PluginLog 'CLAUDE_PLUGIN_ROOT not set - running outside plugin context; skipping.'
    exit 0
}
$pyprojectPath = Join-Path $PluginRoot 'pyproject.toml'
if (-not (Test-Path $pyprojectPath)) {
    Write-PluginLog "Missing pyproject.toml at $PluginRoot - plugin layout broken; skipping."
    exit 0
}

# Parse declared version (line:  version = "X.Y.Z")
$declaredVersion = $null
foreach ($line in Get-Content $pyprojectPath) {
    if ($line -match '^version\s*=\s*"([^"]+)"') {
        $declaredVersion = $Matches[1]
        break
    }
}
if (-not $declaredVersion) {
    Write-PluginLog "Could not parse version from $pyprojectPath; skipping."
    exit 0
}

# 1. Probe pipx ────────────────────────────────────────────────────────────
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-PluginLog 'pipx not found on PATH. Install it first:'
    Write-PluginLog '  python -m pip install --user pipx'
    Write-PluginLog '  python -m pipx ensurepath   # restart shell after'
    Write-PluginLog 'Then this hook will install yt-tools on the next session start.'
    exit 0
}

# 2. Probe yt-tools — install or update from plugin clone ──────────────────
$installedVersion = $null
try {
    $pipxOut = pipx list --short 2>$null
    if ($pipxOut) {
        $line = $pipxOut | Where-Object { $_ -match '^yt-tools\s+' } | Select-Object -First 1
        if ($line) {
            $installedVersion = ($line -split '\s+')[1]
        }
    }
} catch {
    # pipx list error — assume yt-tools missing
}

$needsInstall = $true
if ($installedVersion -and $installedVersion -eq $declaredVersion) {
    $needsInstall = $false
    Write-PluginLog "yt-tools $installedVersion installed from plugin clone - ok"
}

if ($needsInstall) {
    if ($installedVersion) {
        Write-PluginLog "Installed $installedVersion != plugin $declaredVersion; reinstalling from $PluginRoot..."
    } else {
        Write-PluginLog "yt-tools not installed; installing from $PluginRoot via pipx..."
    }
    # --force allows reinstall over existing; installs from the plugin clone
    # itself (not from PyPI). For chord-progression / structure features:
    #   pipx inject yt-tools "bpm-detector @ git+https://github.com/libraz/bpm-detector@v1.1.0"
    try {
        pipx install --force $PluginRoot 2>&1 | ForEach-Object { Write-PluginLog $_ }
    } catch {
        Write-PluginLog "WARN: pipx install from $PluginRoot failed. Investigate pipx state."
    }
}

# 3. Probe ffmpeg ──────────────────────────────────────────────────────────
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-PluginLog 'ffmpeg not on PATH. Install via winget:'
    Write-PluginLog '  winget install Gyan.FFmpeg'
    Write-PluginLog 'Then restart the shell so the new PATH is picked up.'
}

exit 0
