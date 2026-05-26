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

    # Python health probe — bail if the candidate interpreter's stdlib is
    # broken (e.g. uv-toolchain drift leaves SRE magic mismatch and re.compile
    # crashes). Without this we silently replace a working venv with a broken
    # one. YT_TOOLS_PYTHON env-var overrides the probe target and is also
    # forwarded to pipx via --python.
    $probePython = $env:YT_TOOLS_PYTHON
    if (-not $probePython) {
        $probePython = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
    if ($probePython) {
        & $probePython -c "import re; re.compile('x')" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-PluginLog "WARN: $probePython failed health check (import re / re.compile crashed)."
            Write-PluginLog 'Refusing to install - would replace a working pipx venv with a broken interpreter.'
            Write-PluginLog 'Fix: set $env:YT_TOOLS_PYTHON to a known-good python.exe path and restart the session,'
            Write-PluginLog 'or repair the system interpreter (uv toolchain refresh).'
            exit 0
        }
    }

    # Uninstall first if a previous venv exists. pipx `install --force` with
    # the uv backend leaves a previous venv in place ("not created in this
    # session") and the reinstall silently no-ops, so we drop --force in
    # favour of explicit uninstall + clean install. Idempotent (silent if
    # nothing is installed).
    if ($installedVersion) {
        pipx uninstall yt-tools 2>&1 | ForEach-Object { Write-PluginLog $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-PluginLog 'WARN: pipx uninstall yt-tools failed; will attempt install anyway.'
        }
    }

    # Install with [full] extras (chord progression + structure detection via
    # bpm-detector); fall back to core if the VCS dep fetch fails (corporate
    # proxy blocking PEP 508 direct refs, transient network, etc.). Flows A
    # and B work in either mode; Flow C runs librosa-only without [full].
    $pipxArgs = @('install')
    if ($env:YT_TOOLS_PYTHON) {
        $pipxArgs += @('--python', $env:YT_TOOLS_PYTHON)
    }
    $fullTarget = "$PluginRoot[full]"
    pipx @pipxArgs $fullTarget 2>&1 | ForEach-Object { Write-PluginLog $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-PluginLog 'WARN: install with [full] extras failed (likely bpm-detector VCS fetch blocked); falling back to core install.'
        pipx @pipxArgs $PluginRoot 2>&1 | ForEach-Object { Write-PluginLog $_ }
        if ($LASTEXITCODE -ne 0) {
            Write-PluginLog 'WARN: core install also failed. Investigate pipx state.'
        }
    }
}

# 3. Probe ffmpeg ──────────────────────────────────────────────────────────
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-PluginLog 'ffmpeg not on PATH. Install via winget:'
    Write-PluginLog '  winget install Gyan.FFmpeg'
    Write-PluginLog 'Then restart the shell so the new PATH is picked up.'
}

exit 0
