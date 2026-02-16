"""Background worker for update checking. Invoked as subprocess.

This module is designed to run as a detached subprocess to check PyPI for
updates and write to the cache file without blocking CLI execution.

Usage:
    python -m affinity.cli._update_worker --cache-path /path/to/cache.json --current-version 1.6.0
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    """Main entry point for background update worker."""
    parser = argparse.ArgumentParser(description="Background update checker")
    parser.add_argument("--cache-path", required=True, type=Path, help="Path to cache file")
    parser.add_argument(
        "--current-version",
        required=True,
        help="Installed version of affinity-sdk (passed by spawning process)",
    )
    args = parser.parse_args()

    cache_path: Path = args.cache_path
    current: str = args.current_version

    try:
        import httpx
        from packaging.version import Version

        from affinity.cli.update_check import (
            PYPI_URL,
            UpdateInfo,
            get_latest_stable_version,
            save_update_info,
        )

        response = httpx.get(
            PYPI_URL,
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()

        # Filter out pre-releases using shared helper
        latest = get_latest_stable_version(data.get("releases", {}))
        if latest is None:
            # Fallback to info.version if no stable releases found
            latest = data["info"]["version"]

        # Use proper version comparison
        try:
            update_available = Version(latest) > Version(current)
        except Exception:
            update_available = False

        # Use shared save function for atomic writes
        info = UpdateInfo(
            current_version=current,
            latest_version=latest,
            checked_at=datetime.now(timezone.utc),
            update_available=update_available,
        )
        save_update_info(cache_path, info)

    except Exception:
        pass  # Silent failure - never affect CLI operation


if __name__ == "__main__":
    main()
