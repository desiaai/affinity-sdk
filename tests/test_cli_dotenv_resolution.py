"""Tests for --dotenv CWD resolution (upward .env search via find_dotenv).

When --dotenv is used without an explicit --env-file, the CLI should search
upward from CWD for a .env file using python-dotenv's find_dotenv(). This
mirrors the Cowork VM scenario where .env lives in /session/ but CWD is
/session/workdir/.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")
pytest.importorskip("dotenv")

from click.testing import CliRunner

from affinity.cli.context import CLIContext
from affinity.cli.main import cli
from affinity.cli.paths import CliPaths


def _make_mock_paths(base_path: Path) -> CliPaths:
    """Create a CliPaths pointing to a directory inside base_path (no real config)."""
    config_dir = base_path / "xaffinity_config"
    return CliPaths(
        config_dir=config_dir,
        config_path=config_dir / "config.toml",
        cache_dir=base_path / "cache",
        state_dir=base_path / "state",
        log_dir=base_path / "logs",
        log_file=base_path / "logs" / "xaffinity.log",
    )


@contextmanager
def _mock_cli_paths(mock_paths: CliPaths):
    """Context manager to mock CLIContext paths so tests don't read real config."""
    original_init = CLIContext.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        object.__setattr__(self, "_paths", mock_paths)

    with patch.object(CLIContext, "__init__", patched_init):
        yield


@pytest.mark.req("CLI-DOTENV-RESOLUTION")
class TestDotenvResolution:
    """Tests for --dotenv upward search and --env-file explicit path handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_dotenv_finds_env_in_parent_dir(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--dotenv finds .env in parent directory when CWD is a child."""
        # Create .env in parent dir
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".env").write_text("AFFINITY_API_KEY=test-parent-key\n")

        # Create child dir and chdir into it
        child = parent / "child"
        child.mkdir()
        monkeypatch.chdir(child)
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            result = runner.invoke(
                cli,
                ["--dotenv", "--json", "config", "check-key"],
            )
        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
        data = json.loads(result.output.strip())
        assert data["data"]["configured"] is True

    def test_explicit_env_file_dot_env_skips_upward_search(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --env-file .env does NOT search upward; fails if CWD has no .env."""
        # Create .env only in parent dir
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".env").write_text("AFFINITY_API_KEY=test-parent-key\n")

        # Create child dir and chdir into it (no .env here)
        child = parent / "child"
        child.mkdir()
        monkeypatch.chdir(child)
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            result = runner.invoke(
                cli,
                ["--env-file", ".env", "--json", "config", "check-key"],
            )
        # Should fail because explicit --env-file .env means "use ./child/.env"
        # which doesn't exist, and no upward search is performed
        assert result.exit_code != 0, (
            f"Expected non-zero exit, got {result.exit_code}: {result.output}"
        )

    def test_explicit_env_file_enables_dotenv(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --env-file (without --dotenv) implicitly enables dotenv loading."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        # Create .env in CWD
        (tmp_path / ".env").write_text("AFFINITY_API_KEY=test-implicit-key\n")

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            # Pass --env-file .env explicitly (no --dotenv flag)
            result = runner.invoke(
                cli,
                ["--env-file", ".env", "--json", "config", "check-key"],
            )
        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
        data = json.loads(result.output.strip())
        assert data["data"]["configured"] is True

    def test_explicit_env_file_absolute_path(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit --env-file with absolute path works correctly."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        # Create .env at a custom absolute path
        custom_env = tmp_path / "custom" / "my.env"
        custom_env.parent.mkdir(parents=True)
        custom_env.write_text("AFFINITY_API_KEY=test-absolute-key\n")

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            result = runner.invoke(
                cli,
                ["--env-file", str(custom_env), "--json", "config", "check-key"],
            )
        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
        data = json.loads(result.output.strip())
        assert data["data"]["configured"] is True

    def test_dotenv_no_env_file_anywhere_raises(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--dotenv with no .env file anywhere in hierarchy results in error."""
        # Use an empty directory tree
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            result = runner.invoke(
                cli,
                ["--dotenv", "--json", "config", "check-key"],
            )
        assert result.exit_code != 0, (
            f"Expected non-zero exit, got {result.exit_code}: {result.output}"
        )

    def test_cowork_cwd_scenario(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates Cowork VM: .env in /session/, CWD is /session/workdir/."""
        # Simulate the Cowork directory structure
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        (session_dir / ".env").write_text("AFFINITY_API_KEY=test-cowork-key\n")

        workdir = session_dir / "workdir"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        mock_paths = _make_mock_paths(tmp_path / "mock_config")
        with _mock_cli_paths(mock_paths):
            result = runner.invoke(
                cli,
                ["--dotenv", "--json", "config", "check-key"],
            )
        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
        data = json.loads(result.output.strip())
        assert data["data"]["configured"] is True
        assert data["data"]["source"] == "dotenv"
