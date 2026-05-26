#!/usr/bin/env python3
"""yt-tools plugin — SessionStart hook dispatcher (cross-platform).

Claude Code's hook runtime executes the `command` field via the host OS,
so a bare ``.sh`` reference fails silently on Windows (no bash association,
no shebang resolution) and a bare ``.ps1`` reference fails on POSIX. This
shim picks the correct script for the current OS and invokes it directly
so the right interpreter is always in scope.

Always exits 0 — the hook must never block session start. Failures from
the underlying script are logged to stderr (and Claude Code surfaces them
in the session UI), but Python's exit code stays 0 here.

The dispatcher is idempotent: calling it twice in the same session (e.g.
because hooks.json lists both ``python3`` and ``python`` commands as
fallbacks) does a second no-op once the version-match check inside the
underlying script trips.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _log(msg: str) -> None:
    print(f"[yt-tools] {msg}", file=sys.stderr)


def main() -> int:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        _log("CLAUDE_PLUGIN_ROOT not set; running outside plugin context; skipping.")
        return 0

    scripts_dir = Path(plugin_root) / "scripts"

    if os.name == "nt":
        # Prefer PowerShell 7 (`pwsh`) if available, fall back to the
        # built-in Windows PowerShell 5.1 (`powershell.exe`).
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            _log("No PowerShell on PATH (pwsh/powershell); cannot run hook.")
            return 0
        script = scripts_dir / "ensure-install.ps1"
        cmd = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        shell = shutil.which("bash") or "/bin/sh"
        script = scripts_dir / "ensure-install.sh"
        cmd = [shell, str(script)]

    if not script.exists():
        _log(f"Missing {script}; plugin layout broken; skipping.")
        return 0

    try:
        subprocess.run(cmd, check=False)
    except Exception as exc:  # noqa: BLE001 — never block session start
        _log(f"Hook dispatcher failed: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
