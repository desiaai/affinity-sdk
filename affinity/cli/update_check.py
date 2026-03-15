"""CLI auto-update checking module.

This module implements a non-blocking, opt-out update notification system that:
- Never interrupts command execution
- Is invisible to LLMs and automated scripts (--quiet, --output json, no TTY)
- Respects user preferences via config and environment
- Uses industry-standard patterns (npm update-notifier)

See docs/internal/cli-auto-update-implementation-plan.md for design details.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from packaging.version import Version

import affinity

if TYPE_CHECKING:
    from filelock import FileLock

PYPI_URL = "https://pypi.org/pypi/affinity-sdk/json"
CHECK_INTERVAL = timedelta(hours=24)  # Check once per day
NETWORK_TIMEOUT = 3.0  # Fast timeout - don't slow down CLI
NOTIFY_COOLDOWN = timedelta(hours=1)  # Don't spam notifications


@dataclass
class UpdateInfo:
    """Cached update check result."""

    current_version: str
    latest_version: str | None
    checked_at: datetime
    update_available: bool
    last_notified_at: datetime | None = None  # Track when user was last notified

    def is_stale(self) -> bool:
        """Check if the cache is older than CHECK_INTERVAL."""
        now = datetime.now(timezone.utc)
        checked = (
            self.checked_at.replace(tzinfo=timezone.utc)
            if self.checked_at.tzinfo is None
            else self.checked_at
        )
        return now - checked > CHECK_INTERVAL

    def should_notify(self) -> bool:
        """Return True if notification hasn't been shown recently."""
        if self.last_notified_at is None:
            return True
        now = datetime.now(timezone.utc)
        notified = (
            self.last_notified_at.replace(tzinfo=timezone.utc)
            if self.last_notified_at.tzinfo is None
            else self.last_notified_at
        )
        return now - notified > NOTIFY_COOLDOWN


def get_latest_stable_version(releases: dict[str, object]) -> str | None:
    """Extract the latest stable (non-prerelease) version from PyPI releases dict.

    Args:
        releases: The "releases" dict from PyPI JSON API response.

    Returns:
        Latest stable version string, or None if no stable releases found.
    """
    stable_versions = []
    for ver_str in releases:
        try:
            ver = Version(ver_str)
            if not ver.is_prerelease and not ver.is_devrelease:
                stable_versions.append(ver)
        except Exception:
            continue  # Skip invalid version strings

    if stable_versions:
        return str(max(stable_versions))
    return None


def check_pypi_version(*, include_prereleases: bool = False) -> str | None:
    """Query PyPI for latest stable version. Returns None on any error.

    Args:
        include_prereleases: If True, include pre-release versions (alpha, beta, rc).
                           Default is False to avoid notifying users about unstable releases.
    """
    try:
        with httpx.Client(timeout=NETWORK_TIMEOUT) as client:
            response = client.get(PYPI_URL)
            response.raise_for_status()
            data = response.json()

            if include_prereleases:
                # Just return the latest version (what PyPI reports)
                return str(data["info"]["version"])

            # Filter out pre-releases using shared helper
            latest_stable = get_latest_stable_version(data.get("releases", {}))
            if latest_stable:
                return latest_stable

            # Fallback to info.version if no stable releases found
            return str(data["info"]["version"])
    except Exception:
        return None


def get_cached_update_info(cache_path: Path) -> UpdateInfo | None:
    """Load cached update info. Returns None if cache is invalid or for different version."""
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        last_notified_raw = data.get("last_notified_at")
        info = UpdateInfo(
            current_version=data["current_version"],
            latest_version=data.get("latest_version"),
            checked_at=datetime.fromisoformat(data["checked_at"]),
            update_available=data.get("update_available", False),
            last_notified_at=(
                datetime.fromisoformat(last_notified_raw) if last_notified_raw else None
            ),
        )
        # Version-aware cache handling
        installed = affinity.__version__
        if info.current_version != installed:
            try:
                if Version(info.current_version) < Version(installed):
                    # User upgraded — clear update flag, keep cache metadata
                    return UpdateInfo(
                        current_version=installed,
                        latest_version=info.latest_version,
                        checked_at=info.checked_at,
                        update_available=False,
                        last_notified_at=None,
                    )
                else:
                    # Cached version > installed — downgraded or different install
                    return None
            except Exception:
                return None  # Invalid version strings, invalidate
        return info
    except Exception:
        return None


def save_update_info(cache_path: Path, info: UpdateInfo) -> None:
    """Save update info to cache atomically.

    Uses write-to-temp-then-rename pattern for atomic updates, preventing
    corruption if the process is interrupted mid-write.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "current_version": info.current_version,
        "latest_version": info.latest_version,
        "checked_at": info.checked_at.isoformat(),
        "update_available": info.update_available,
        "last_notified_at": (info.last_notified_at.isoformat() if info.last_notified_at else None),
    }

    # Write to temporary file first, then atomically rename
    # This prevents partial reads if process is killed mid-write
    from contextlib import suppress

    try:
        fd, tmp_path_str = tempfile.mkstemp(
            dir=cache_path.parent,
            prefix=".update_check_",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            # Set permissions before rename (so file is never world-readable)
            with suppress(OSError):
                tmp_path.chmod(0o600)
            # Atomic rename (POSIX guarantees atomicity for same-filesystem rename)
            tmp_path.replace(cache_path)
        except Exception:
            # Clean up temp file on error
            with suppress(OSError):
                tmp_path.unlink()
            raise
    except Exception:
        pass  # Silent failure - never affect CLI operation


def is_update_available(current: str, latest: str) -> bool:
    """Compare versions using packaging library."""
    try:
        return bool(Version(latest) > Version(current))
    except Exception:
        return False


def acquire_update_lock(state_dir: Path) -> FileLock | None:
    """Try to acquire update check lock. Returns lock if acquired, None otherwise.

    Uses filelock library for cross-platform support. The returned lock
    must be kept alive for the duration of the operation (don't let it
    go out of scope, or the lock will be released).

    Returns:
        FileLock instance if acquired, None if another process holds the lock.
    """
    from filelock import FileLock, Timeout

    lock_path = state_dir / "update_check.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=0)  # Non-blocking
    try:
        lock.acquire()
        return lock
    except Timeout:
        return None  # Another process is already checking


def get_upgrade_command() -> str:
    """Detect installation method and return appropriate upgrade command.

    Checks for tool-based installations (pipx, uv tool) first since they
    preserve extras during upgrade. Falls back to pip/uv pip commands.

    Returns:
        Upgrade command string (e.g., "pipx upgrade affinity-sdk").
    """
    import shutil

    # Check pipx first (preferred for CLI tools)
    # pipx preserves extras during upgrade, so no need to specify [cli]
    if shutil.which("pipx"):
        try:
            result = subprocess.run(
                ["pipx", "list", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if "affinity-sdk" in result.stdout:
                return "pipx upgrade affinity-sdk"
        except Exception:
            pass

    # Check uv tool installation (similar to pipx)
    # uv tool preserves extras during upgrade
    if shutil.which("uv"):
        try:
            result = subprocess.run(
                ["uv", "tool", "list"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if "affinity-sdk" in result.stdout:
                return "uv tool upgrade affinity-sdk"
        except Exception:
            pass

    # Package spec includes [cli] since user is running CLI commands
    # This ensures CLI dependencies are preserved during upgrade
    pkg_spec = '"affinity-sdk[cli]"'

    # Check uv pip (fast Python package installer, but not tool mode)
    if shutil.which("uv"):
        return f"uv pip install --upgrade {pkg_spec}"

    # Determine pip command - prefer pip3 on systems where pip might be Python 2
    # Check pip3 first (more likely to be Python 3 on dual-install systems)
    pip_cmd = "pip"
    if shutil.which("pip3"):
        pip_cmd = "pip3"
    elif not shutil.which("pip"):
        # Neither pip nor pip3 found, fall back to python -m pip
        pip_cmd = "python3 -m pip" if shutil.which("python3") else "python -m pip"

    # Default to pip/pip3
    return f"{pip_cmd} install --upgrade {pkg_spec}"


def render_update_notification(current: str, latest: str) -> None:
    """Render update notification to stderr. Uses Rich if available."""
    upgrade_cmd = get_upgrade_command()
    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console(stderr=True)
        console.print()
        console.print(
            Panel(
                f"[bold]Update available:[/bold] {current} → [green]{latest}[/green]\n"
                f"Run: [cyan]{upgrade_cmd}[/cyan]",
                title="xaffinity",
                border_style="dim",
            )
        )
    except ImportError:
        # Fallback to plain text if Rich unavailable
        _render_update_notification_plain(current, latest, upgrade_cmd)


def _render_update_notification_plain(
    current: str, latest: str, upgrade_cmd: str | None = None
) -> None:
    """Plain-text fallback notification."""
    if upgrade_cmd is None:
        upgrade_cmd = get_upgrade_command()
    # Calculate dynamic width based on version strings
    content_line = f"  Update available: {current} → {latest}  "
    cmd_line = f"  Run: {upgrade_cmd}  "
    width = max(len(content_line), len(cmd_line))

    sys.stderr.write("\n")
    sys.stderr.write(f"┌{'─' * width}┐\n")
    sys.stderr.write(f"│{content_line:<{width}}│\n")
    sys.stderr.write(f"│{cmd_line:<{width}}│\n")
    sys.stderr.write(f"└{'─' * width}┘\n")
    sys.stderr.flush()


def check_for_update_interactive(state_dir: Path) -> None:
    """Check for updates and display notification if available.

    This function:
    1. Reads cached update info (no network call on critical path)
    2. Displays notification if update is available (respects cooldown)
    3. Triggers background refresh if cache is stale

    Args:
        state_dir: Platform-appropriate state directory from CliPaths.
    """
    cache_path = state_dir / "update_check.json"

    # Read cached info (fast, no network)
    cached = get_cached_update_info(cache_path)

    if cached is not None:
        # Show notification if update available AND cooldown has passed
        if cached.update_available and cached.latest_version and cached.should_notify():
            render_update_notification(
                current=cached.current_version,
                latest=cached.latest_version,
            )
            # Update last_notified_at to prevent spamming
            updated = UpdateInfo(
                current_version=cached.current_version,
                latest_version=cached.latest_version,
                checked_at=cached.checked_at,
                update_available=cached.update_available,
                last_notified_at=datetime.now(timezone.utc),
            )
            save_update_info(cache_path, updated)

        # Trigger background refresh if cache is stale
        if cached.is_stale():
            trigger_background_update_check(state_dir, current_version=affinity.__version__)
    else:
        # No cache - trigger background check for next time
        trigger_background_update_check(state_dir, current_version=affinity.__version__)


def trigger_background_update_check(state_dir: Path, *, current_version: str | None = None) -> None:
    """Spawn background process to update cache.

    Args:
        state_dir: Platform-appropriate state directory from CliPaths.
        current_version: Version string to pass to worker. Falls back to
            affinity.__version__ if not provided (backward compat).
    """
    # Don't spawn if another check is already running
    lock = acquire_update_lock(state_dir)
    if lock is None:
        return

    # Lock prevents multiple rapid CLI invocations from spawning duplicate workers.
    # The background worker runs independently (no lock needed for cache writes -
    # it uses atomic file operations).

    cache_path = state_dir / "update_check.json"

    version = current_version or affinity.__version__

    # Build subprocess arguments
    cmd = [
        sys.executable,
        "-m",
        "affinity.cli._update_worker",
        "--cache-path",
        str(cache_path),
        "--current-version",
        version,
    ]

    try:
        if platform.system() == "Windows":
            # Windows: use creation flags for proper detachment
            # These constants are Windows-specific
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            )
        else:
            # Unix: start new session to detach from terminal
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:
        pass  # Silent failure - never affect CLI operation

    # Release lock - worker will run independently
    lock.release()
