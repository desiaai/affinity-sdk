"""Tests for CLI auto-update checking module."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from affinity.cli.update_check import (
    UpdateInfo,
    _render_update_notification_plain,
    acquire_update_lock,
    check_for_update_interactive,
    get_cached_update_info,
    get_latest_stable_version,
    is_update_available,
    render_update_notification,
    save_update_info,
    trigger_background_update_check,
)


class TestVersionComparison:
    """Tests for is_update_available()."""

    def test_patch_update_available(self):
        assert is_update_available("0.9.0", "0.9.1") is True

    def test_minor_update_available(self):
        assert is_update_available("0.9.1", "0.10.0") is True

    def test_major_update_available(self):
        assert is_update_available("0.9.1", "1.0.0") is True

    def test_no_update_when_same_version(self):
        assert is_update_available("0.9.1", "0.9.1") is False

    def test_no_update_when_newer(self):
        assert is_update_available("0.9.1", "0.9.0") is False

    def test_handles_prerelease_versions(self):
        assert is_update_available("0.9.1a1", "0.9.1") is True
        assert is_update_available("0.9.1", "0.9.2a1") is True

    def test_handles_invalid_versions_gracefully(self):
        # Should return False, not raise
        assert is_update_available("invalid", "0.9.1") is False
        assert is_update_available("0.9.1", "invalid") is False


class TestGetLatestStableVersion:
    """Tests for get_latest_stable_version()."""

    def test_filters_prereleases(self):
        releases = {
            "0.9.0": [],
            "0.9.1": [],
            "1.0.0a1": [],  # Pre-release
            "1.0.0b1": [],  # Pre-release
            "1.0.0rc1": [],  # Pre-release
        }
        assert get_latest_stable_version(releases) == "0.9.1"

    def test_returns_latest_stable(self):
        releases = {
            "0.9.0": [],
            "0.10.0": [],
            "1.0.0": [],
        }
        assert get_latest_stable_version(releases) == "1.0.0"

    def test_handles_empty_releases(self):
        assert get_latest_stable_version({}) is None

    def test_handles_only_prereleases(self):
        releases = {
            "1.0.0a1": [],
            "1.0.0b1": [],
        }
        assert get_latest_stable_version(releases) is None

    def test_handles_invalid_versions(self):
        releases = {
            "invalid": [],
            "0.9.0": [],
        }
        assert get_latest_stable_version(releases) == "0.9.0"


class TestUpdateInfo:
    """Tests for UpdateInfo dataclass."""

    def test_is_stale_when_old(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=old_time,
            update_available=True,
        )
        assert info.is_stale() is True

    def test_is_not_stale_when_recent(self):
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=recent_time,
            update_available=True,
        )
        assert info.is_stale() is False

    def test_should_notify_when_never_notified(self):
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
            last_notified_at=None,
        )
        assert info.should_notify() is True

    def test_should_not_notify_when_recently_notified(self):
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
            last_notified_at=recent_time,
        )
        assert info.should_notify() is False

    def test_should_notify_after_cooldown(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
            last_notified_at=old_time,
        )
        assert info.should_notify() is True


class TestCacheRoundtrip:
    """Tests for cache save/load."""

    def test_cache_roundtrip(self, tmp_path):
        import affinity

        cache_path = tmp_path / "update_check.json"
        info = UpdateInfo(
            current_version=affinity.__version__,  # Use actual version
            latest_version="99.0.0",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
        )
        save_update_info(cache_path, info)
        loaded = get_cached_update_info(cache_path)
        assert loaded is not None
        assert loaded.update_available is True
        assert loaded.latest_version == "99.0.0"

    def test_cache_roundtrip_with_notification_time(self, tmp_path):
        import affinity

        cache_path = tmp_path / "update_check.json"
        notified_at = datetime.now(timezone.utc)
        info = UpdateInfo(
            current_version=affinity.__version__,  # Use actual version
            latest_version="99.0.0",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
            last_notified_at=notified_at,
        )
        save_update_info(cache_path, info)
        loaded = get_cached_update_info(cache_path)
        assert loaded is not None
        assert loaded.last_notified_at is not None

    def test_cache_adapted_when_user_upgraded(self, tmp_path):
        """Cache should be adapted (not invalidated) if user upgraded since last check."""
        cache_path = tmp_path / "update_check.json"
        info = UpdateInfo(
            current_version="0.1.0",  # Old version — lower than any real installed version
            latest_version="0.9.0",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
        )
        save_update_info(cache_path, info)

        # Since 0.1.0 < installed version, cache should be adapted (not None)
        loaded = get_cached_update_info(cache_path)
        assert loaded is not None
        # The adapted cache should reflect the installed version
        import affinity

        assert loaded.current_version == affinity.__version__
        # update_available should be cleared (can't know until next check)
        assert loaded.update_available is False
        # last_notified_at should be reset
        assert loaded.last_notified_at is None
        # latest_version should be preserved from original cache
        assert loaded.latest_version == "0.9.0"

    def test_cache_invalidated_when_downgraded(self, tmp_path):
        """Cache invalidated when cached version > installed (downgrade)."""
        cache_path = tmp_path / "update_check.json"
        info = UpdateInfo(
            current_version="999.0.0",  # Higher than any real installed version
            latest_version="999.0.1",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
        )
        save_update_info(cache_path, info)

        # Since 999.0.0 > installed version, cache should be invalidated
        assert get_cached_update_info(cache_path) is None

    def test_cache_invalidated_when_version_invalid(self, tmp_path):
        """Cache should be invalidated if cached version string is unparseable."""
        import json as json_mod

        cache_path = tmp_path / "update_check.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_version": "not-a-version",
            "latest_version": "1.0.0",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "update_available": True,
            "last_notified_at": None,
        }
        cache_path.write_text(json_mod.dumps(data), encoding="utf-8")

        assert get_cached_update_info(cache_path) is None

    def test_stale_cache_detected(self, tmp_path):
        cache_path = tmp_path / "update_check.json"
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=old_time,
            update_available=True,
        )
        save_update_info(cache_path, info)

        # Load cache manually to check staleness
        data = json.loads(cache_path.read_text())
        loaded_info = UpdateInfo(
            current_version=data["current_version"],
            latest_version=data.get("latest_version"),
            checked_at=datetime.fromisoformat(data["checked_at"]),
            update_available=data.get("update_available", False),
        )
        assert loaded_info.is_stale() is True

    def test_cache_missing_returns_none(self, tmp_path):
        cache_path = tmp_path / "nonexistent.json"
        assert get_cached_update_info(cache_path) is None

    def test_cache_corrupt_returns_none(self, tmp_path):
        cache_path = tmp_path / "corrupt.json"
        cache_path.write_text("not valid json {{{")
        assert get_cached_update_info(cache_path) is None

    def test_save_creates_parent_dirs(self, tmp_path):
        cache_path = tmp_path / "nested" / "dirs" / "update_check.json"
        info = UpdateInfo(
            current_version="0.9.0",
            latest_version="0.9.1",
            checked_at=datetime.now(timezone.utc),
            update_available=True,
        )
        save_update_info(cache_path, info)
        assert cache_path.exists()


class TestLockMechanism:
    """Tests for concurrent check prevention."""

    def test_acquire_lock_succeeds_when_free(self, tmp_path):
        lock = acquire_update_lock(tmp_path)
        assert lock is not None
        lock.release()

    def test_acquire_lock_fails_when_held(self, tmp_path):
        # First acquisition succeeds
        lock1 = acquire_update_lock(tmp_path)
        assert lock1 is not None

        # Second acquisition fails (non-blocking)
        lock2 = acquire_update_lock(tmp_path)
        assert lock2 is None

        # After releasing first lock, acquisition succeeds
        lock1.release()
        lock3 = acquire_update_lock(tmp_path)
        assert lock3 is not None
        lock3.release()


class TestNotificationRendering:
    """Tests for notification rendering."""

    def test_plain_notification_output(self, capsys):
        _render_update_notification_plain("0.9.0", "1.0.0")
        captured = capsys.readouterr()
        assert "Update available" in captured.err
        assert "0.9.0" in captured.err
        assert "1.0.0" in captured.err
        # Check for upgrade command - exact command varies by environment (pip/pip3/uv/pipx)
        assert "affinity-sdk" in captured.err
        # Should include install/upgrade keywords
        assert "install" in captured.err or "upgrade" in captured.err

    def test_render_notification_uses_rich_when_available(self):
        # Just verify it doesn't crash
        with patch("sys.stderr.isatty", return_value=True):
            try:
                render_update_notification("0.9.0", "1.0.0")
            except Exception:
                pytest.fail("render_update_notification should not raise")


class TestBackgroundCheckIntegration:
    """Integration tests for background update checking."""

    def test_trigger_background_check_acquires_lock(self, tmp_path):
        """Verify background check acquires and releases lock."""
        with patch("subprocess.Popen"):
            trigger_background_update_check(tmp_path, current_version="1.0.0")
            # Lock should be released after subprocess spawn
            lock = acquire_update_lock(tmp_path)
            assert lock is not None
            lock.release()

    def test_trigger_background_check_passes_current_version(self, tmp_path):
        """Verify background check passes --current-version to subprocess."""
        with patch("subprocess.Popen") as mock_popen:
            trigger_background_update_check(tmp_path, current_version="1.6.0")
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert "--current-version" in cmd
            version_idx = cmd.index("--current-version")
            assert cmd[version_idx + 1] == "1.6.0"

    def test_trigger_background_check_falls_back_to_affinity_version(self, tmp_path):
        """Verify background check uses affinity.__version__ when no version given."""
        import affinity

        with patch("subprocess.Popen") as mock_popen:
            trigger_background_update_check(tmp_path)
            mock_popen.assert_called_once()
            cmd = mock_popen.call_args[0][0]
            assert "--current-version" in cmd
            version_idx = cmd.index("--current-version")
            assert cmd[version_idx + 1] == affinity.__version__

    def test_trigger_background_check_skips_when_locked(self, tmp_path):
        """Verify background check skips when another process holds lock."""
        # Acquire lock first
        lock = acquire_update_lock(tmp_path)
        assert lock is not None

        with patch("subprocess.Popen") as mock_popen:
            trigger_background_update_check(tmp_path)
            # Should not spawn subprocess
            mock_popen.assert_not_called()

        lock.release()

    def test_check_for_update_interactive_no_cache(self, tmp_path):
        """Verify interactive check triggers background when no cache."""
        import affinity

        with patch("affinity.cli.update_check.trigger_background_update_check") as mock_trigger:
            check_for_update_interactive(tmp_path)
            mock_trigger.assert_called_once_with(tmp_path, current_version=affinity.__version__)

    def test_check_for_update_interactive_with_fresh_cache_no_update(self, tmp_path):
        """Verify no notification when cache says no update."""
        cache_path = tmp_path / "update_check.json"

        # Create fresh cache with no update
        import affinity

        info = UpdateInfo(
            current_version=affinity.__version__,
            latest_version=affinity.__version__,
            checked_at=datetime.now(timezone.utc),
            update_available=False,
        )
        save_update_info(cache_path, info)

        with patch("affinity.cli.update_check.render_update_notification") as mock_notify:
            check_for_update_interactive(tmp_path)
            mock_notify.assert_not_called()


class TestShouldCheckForUpdates:
    """Tests for _should_check_for_updates() in main.py."""

    def test_suppressed_when_quiet(self):
        """Verify update check is suppressed with --quiet."""
        from affinity.cli.main import _should_check_for_updates

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = True
        click_ctx.obj.output = None
        click_ctx.obj.update_check_enabled = True

        assert _should_check_for_updates(click_ctx) is False

    def test_suppressed_for_json_output(self):
        """Verify update check is suppressed with --output json."""
        from affinity.cli.main import _should_check_for_updates

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "json"
        click_ctx.obj.update_check_enabled = True

        assert _should_check_for_updates(click_ctx) is False

    def test_suppressed_in_ci(self, monkeypatch):
        """Verify update check is suppressed in CI environments."""
        from affinity.cli.main import _should_check_for_updates

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "table"
        click_ctx.obj.update_check_enabled = True

        for var in ("CI", "GITHUB_ACTIONS", "GITLAB_CI"):
            monkeypatch.setenv(var, "true")
            with patch("sys.stderr.isatty", return_value=True):
                assert _should_check_for_updates(click_ctx) is False
            monkeypatch.delenv(var)

    def test_suppressed_without_tty(self):
        """Verify update check is suppressed without TTY."""
        from affinity.cli.main import _should_check_for_updates

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "table"
        click_ctx.obj.update_check_enabled = True

        with patch("sys.stderr.isatty", return_value=False):
            assert _should_check_for_updates(click_ctx) is False

    def test_suppressed_by_env_var(self, monkeypatch):
        """Verify update check is suppressed by XAFFINITY_NO_UPDATE_CHECK."""
        from affinity.cli.main import _should_check_for_updates

        monkeypatch.setenv("XAFFINITY_NO_UPDATE_CHECK", "1")

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "table"
        click_ctx.obj.update_check_enabled = True

        with patch("sys.stderr.isatty", return_value=True):
            assert _should_check_for_updates(click_ctx) is False

    def test_suppressed_by_config(self):
        """Verify update check is suppressed by config setting."""
        from affinity.cli.main import _should_check_for_updates

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "table"
        click_ctx.obj.update_check_enabled = False  # Disabled in config

        with patch("sys.stderr.isatty", return_value=True):
            assert _should_check_for_updates(click_ctx) is False

    def test_enabled_when_interactive(self, monkeypatch):
        """Verify update check is enabled in interactive mode."""
        from affinity.cli.main import _should_check_for_updates

        # Clear any CI env vars
        for var in ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "XAFFINITY_NO_UPDATE_CHECK"):
            monkeypatch.delenv(var, raising=False)

        click_ctx = MagicMock()
        click_ctx.resilient_parsing = False
        click_ctx.obj = MagicMock()
        click_ctx.obj.quiet = False
        click_ctx.obj.output = "table"
        click_ctx.obj.update_check_enabled = True

        with patch("sys.stderr.isatty", return_value=True):
            assert _should_check_for_updates(click_ctx) is True


class TestUpdateWorker:
    """Tests for background update worker module."""

    def test_worker_subprocess_runs_without_crash(self, tmp_path):
        """Verify worker subprocess can be invoked without crashing.

        This tests the subprocess mechanics, not the actual network call.
        We use network isolation to make it fail quickly and silently.
        """
        import subprocess
        import sys

        import affinity

        cache_path = tmp_path / "update_check.json"

        # Run worker with invalid proxy to force quick network failure
        # The worker should handle this gracefully (exit 0, no output)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "affinity.cli._update_worker",
                "--cache-path",
                str(cache_path),
                "--current-version",
                affinity.__version__,
            ],
            check=False,
            capture_output=True,
            timeout=10,
            env={**os.environ, "https_proxy": "http://invalid.proxy:9999"},
        )

        # Should exit cleanly (returncode 0) even on network failure
        assert result.returncode == 0
        # Should not produce any output (silent failure)
        assert result.stdout == b""
        assert result.stderr == b""

    def test_worker_rejects_missing_current_version(self, tmp_path):
        """Verify worker exits with error if --current-version is missing."""
        import subprocess
        import sys

        cache_path = tmp_path / "update_check.json"

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "affinity.cli._update_worker",
                "--cache-path",
                str(cache_path),
            ],
            check=False,
            capture_output=True,
            timeout=10,
        )

        # argparse exits with code 2 for missing required args
        assert result.returncode == 2


class TestUpdateCheckStatusJsonContract:
    """Tests for JSON field contract of `config update-check --status --json`.

    These tests ensure the JSON output always contains required fields that
    MCP and other automation tools depend on.
    """

    def test_status_json_contains_required_fields_without_cache(self, tmp_path, monkeypatch):
        """Verify required fields are present when no cache exists."""
        from click.testing import CliRunner

        from affinity.cli.main import cli
        from affinity.cli.paths import CliPaths

        # Ensure no existing config interferes
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        # Use isolated paths (XDG env vars are ignored on macOS by PlatformDirs)
        mock_paths = CliPaths(
            config_dir=tmp_path / "config",
            config_path=tmp_path / "config" / "config.toml",
            cache_dir=tmp_path / "cache",
            state_dir=tmp_path / "state",
            log_dir=tmp_path / "logs",
            log_file=tmp_path / "logs" / "xaffinity.log",
        )

        runner = CliRunner()
        with patch("affinity.cli.main.get_paths", return_value=mock_paths):
            result = runner.invoke(cli, ["--json", "config", "update-check", "--status"])

        # Command should succeed
        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Parse JSON output
        data = json.loads(result.output)["data"]

        # Required fields for MCP compatibility
        assert "update_check_enabled" in data, "Missing update_check_enabled field"
        assert "update_notify_mode" in data, "Missing update_notify_mode field"
        assert "cache_stale" in data, "Missing cache_stale field"
        assert "state_dir" in data, "Missing state_dir field"

        # When no cache, cache_stale should be True
        assert data["cache_stale"] is True

    def test_status_json_contains_required_fields_with_cache(self, tmp_path):
        """Verify required fields are present when cache exists."""
        from click.testing import CliRunner

        import affinity
        from affinity.cli.main import cli
        from affinity.cli.paths import CliPaths

        # Create isolated paths
        state_dir = tmp_path / "state"
        config_dir = tmp_path / "config"

        mock_paths = CliPaths(
            config_dir=config_dir,
            config_path=config_dir / "config.toml",
            cache_dir=tmp_path / "cache",
            state_dir=state_dir,
            log_dir=tmp_path / "logs",
            log_file=tmp_path / "logs" / "xaffinity.log",
        )

        # Create a fresh cache file
        cache_path = state_dir / "update_check.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        info = UpdateInfo(
            current_version=affinity.__version__,
            latest_version=affinity.__version__,
            checked_at=recent_time,
            update_available=False,
        )
        save_update_info(cache_path, info)

        runner = CliRunner()
        # Mock get_paths to return our test paths
        with patch("affinity.cli.main.get_paths", return_value=mock_paths):
            result = runner.invoke(cli, ["--json", "config", "update-check", "--status"])

        assert result.exit_code == 0, f"Command failed: {result.output}"

        data = json.loads(result.output)["data"]

        # Required fields
        assert "update_check_enabled" in data
        assert "update_notify_mode" in data
        assert "cache_stale" in data
        assert "state_dir" in data

        # With fresh cache, cache_stale should be False
        assert data["cache_stale"] is False

    def test_background_flag_spawns_subprocess(self, tmp_path, monkeypatch):
        """Verify --background flag spawns subprocess and exits silently."""
        from click.testing import CliRunner

        from affinity.cli.main import cli
        from affinity.cli.paths import CliPaths

        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        mock_paths = CliPaths(
            config_dir=tmp_path / "config",
            config_path=tmp_path / "config" / "config.toml",
            cache_dir=tmp_path / "cache",
            state_dir=tmp_path / "state",
            log_dir=tmp_path / "logs",
            log_file=tmp_path / "logs" / "xaffinity.log",
        )

        runner = CliRunner()

        # Mock subprocess.Popen to avoid actually spawning background process
        with (
            patch("affinity.cli.main.get_paths", return_value=mock_paths),
            patch("subprocess.Popen") as mock_popen,
        ):
            result = runner.invoke(cli, ["config", "update-check", "--background"])

            # Verify subprocess was spawned
            mock_popen.assert_called_once()

        # Should succeed silently
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_mutual_exclusion_now_status(self, tmp_path):
        """Verify --now and --status are mutually exclusive."""
        from click.testing import CliRunner

        from affinity.cli.main import cli
        from affinity.cli.paths import CliPaths

        mock_paths = CliPaths(
            config_dir=tmp_path / "config",
            config_path=tmp_path / "config" / "config.toml",
            cache_dir=tmp_path / "cache",
            state_dir=tmp_path / "state",
            log_dir=tmp_path / "logs",
            log_file=tmp_path / "logs" / "xaffinity.log",
        )

        runner = CliRunner()
        with patch("affinity.cli.main.get_paths", return_value=mock_paths):
            result = runner.invoke(cli, ["config", "update-check", "--now", "--status"])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_mutual_exclusion_action_with_enable(self, tmp_path):
        """Verify action flags cannot be combined with --enable/--disable."""
        from click.testing import CliRunner

        from affinity.cli.main import cli
        from affinity.cli.paths import CliPaths

        mock_paths = CliPaths(
            config_dir=tmp_path / "config",
            config_path=tmp_path / "config" / "config.toml",
            cache_dir=tmp_path / "cache",
            state_dir=tmp_path / "state",
            log_dir=tmp_path / "logs",
            log_file=tmp_path / "logs" / "xaffinity.log",
        )

        runner = CliRunner()
        with patch("affinity.cli.main.get_paths", return_value=mock_paths):
            result = runner.invoke(cli, ["config", "update-check", "--status", "--enable"])

        assert result.exit_code != 0
        assert "cannot combine" in result.output.lower()
