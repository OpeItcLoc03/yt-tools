# yt-tools plugin — SessionStart hook (PowerShell variant for Windows).
#
# Idempotent ensure-install: on every session start, verify that the
# yt-tools PyPI package is installed via pipx at >= $PluginVersion, and
# that ffmpeg is on PATH. Print install hints when something is missing;
# never block session start (always exit 0, errors go to stderr).
#
# Invoked manually on Windows if hooks.json's POSIX command does not run:
#   pwsh -File "$env:CLAUDE_PLUGIN_ROOT/scripts/ensure-install.ps1"

$ErrorActionPreference = 'Continue'
$PluginVersion = '0.3.0'

function Write-PluginLog {
    param([string]$Message)
    [Console]::Error.WriteLine("[yt-tools] $Message")
}

# 1. Probe pipx ────────────────────────────────────────────────────────────
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-PluginLog 'pipx not found on PATH. Install it first:'
    Write-PluginLog '  python -m pip install --user pipx'
    Write-PluginLog '  python -m pipx ensurepath   # restart shell after'
    Write-PluginLog 'Then this hook will install yt-tools on the next session start.'
    exit 0
}

# 2. Probe yt-tools via pipx list ──────────────────────────────────────────
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
if ($installedVersion) {
    try {
        $installed = [version]$installedVersion
        $required  = [version]$PluginVersion
        if ($installed -ge $required) {
            $needsInstall = $false
            Write-PluginLog "yt-tools $installedVersion installed (>= plugin $PluginVersion) - ok"
        }
    } catch {
        # version parse failed — fall through to install path
    }
}

if ($needsInstall) {
    if ($installedVersion) {
        Write-PluginLog "yt-tools $installedVersion < $PluginVersion; upgrading via pipx..."
        try { pipx upgrade yt-tools 2>&1 | ForEach-Object { Write-PluginLog $_ } }
        catch { Write-PluginLog 'WARN: pipx upgrade yt-tools failed. Investigate manually.' }
    } else {
        Write-PluginLog 'yt-tools not installed; installing via pipx...'
        try { pipx install yt-tools 2>&1 | ForEach-Object { Write-PluginLog $_ } }
        catch { Write-PluginLog 'WARN: pipx install yt-tools failed. Check PyPI access and pipx state.' }
    }
}

# 3. Probe ffmpeg ──────────────────────────────────────────────────────────
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-PluginLog 'ffmpeg not on PATH. Install via winget:'
    Write-PluginLog '  winget install Gyan.FFmpeg'
    Write-PluginLog 'Then restart the shell so the new PATH is picked up.'
}

exit 0
