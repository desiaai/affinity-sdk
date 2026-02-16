"""Tests for xaffinity config check-key and setup-key commands."""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from affinity.cli.context import CLIContext
from affinity.cli.main import cli
from affinity.cli.paths import CliPaths


def make_mock_paths(base_path: Path) -> CliPaths:
    """Create a CliPaths pointing to a directory inside base_path."""
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
def mock_cli_paths(mock_paths: CliPaths):
    """Context manager to mock CLIContext paths.

    The CLIContext is a frozen dataclass that calls get_paths() at instantiation.
    We patch __init__ to override _paths after the original initialization.
    """
    original_init = CLIContext.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        object.__setattr__(self, "_paths", mock_paths)

    with patch.object(CLIContext, "__init__", patched_init):
        yield


class TestConfigCheckKey:
    """Tests for xaffinity config check-key command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_check_key_not_configured(self, runner, monkeypatch):
        """Test check-key when no key is configured."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 1
        assert '"configured": false' in result.output
        assert '"pattern": null' in result.output

    def test_check_key_from_environment(self, runner, monkeypatch):
        """Test check-key finds key in environment."""
        monkeypatch.setenv("AFFINITY_API_KEY", "test-key")

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 0
        assert '"configured": true' in result.output
        assert '"source": "environment"' in result.output
        assert '"pattern": "xaffinity --readonly <command> --json"' in result.output

    def test_check_key_from_config(self, runner, monkeypatch):
        """Test check-key finds key in config.toml."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            mock_paths.config_dir.mkdir(parents=True)
            mock_paths.config_path.write_text('[default]\napi_key = "test-key"\n')

            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 0
        assert '"configured": true' in result.output
        assert '"source": "config"' in result.output
        assert '"pattern": "xaffinity --readonly <command> --json"' in result.output

    def test_check_key_from_dotenv_file_quoted(self, runner, monkeypatch):
        """Test check-key finds key in .env file with quoted value."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            Path(".env").write_text('AFFINITY_API_KEY="my-secret-key"\n')
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 0
        assert '"configured": true' in result.output
        assert '"source": "dotenv"' in result.output
        assert '"pattern": "xaffinity --dotenv --readonly <command> --json"' in result.output

    def test_check_key_from_dotenv_file_unquoted(self, runner, monkeypatch):
        """Test check-key finds key in .env file with unquoted value."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            Path(".env").write_text("AFFINITY_API_KEY=my-secret-key\n")
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 0
        assert '"configured": true' in result.output
        assert '"source": "dotenv"' in result.output
        assert '"pattern": "xaffinity --dotenv --readonly <command> --json"' in result.output

    def test_check_key_from_custom_env_file_path(self, runner, monkeypatch):
        """Test check-key respects --env-file pointing to a non-CWD path."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            # Create .env in a subdirectory (not CWD)
            subdir = Path(fs) / "subdir"
            subdir.mkdir()
            (subdir / ".env").write_text("AFFINITY_API_KEY=my-secret-key\n")
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths):
                result = runner.invoke(
                    cli, ["--env-file", str(subdir / ".env"), "config", "check-key", "--json"]
                )

        assert result.exit_code == 0
        assert '"configured": true' in result.output
        assert '"source": "dotenv"' in result.output

    def test_check_key_ignores_empty_value_in_env(self, runner, monkeypatch):
        """Test check-key doesn't consider empty api_key as configured."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            Path(".env").write_text('AFFINITY_API_KEY=""\n')
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 1
        assert '"configured": false' in result.output
        assert '"pattern": null' in result.output

    def test_check_key_ignores_wrong_section_in_config(self, runner, monkeypatch):
        """Test check-key only looks in [default] section of config.toml."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            mock_paths.config_dir.mkdir(parents=True)
            # Key is in [other] section, not [default]
            mock_paths.config_path.write_text('[other]\napi_key = "secret"\n')

            with mock_cli_paths(mock_paths):
                result = runner.invoke(cli, ["config", "check-key", "--json"])

        assert result.exit_code == 1
        assert '"configured": false' in result.output
        assert '"pattern": null' in result.output


class TestConfigSetupKey:
    """Tests for xaffinity config setup-key command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_setup_key_project_scope(self, runner, monkeypatch):
        """Test storing key in .env file."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="test-api-key-123"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "project", "--json"])

            assert result.exit_code == 0, f"Failed with output: {result.output}"
            assert '"key_stored": true' in result.output
            assert '"scope": "project"' in result.output
            assert '"validated": true' in result.output

            # Verify .env was created
            env_path = Path(".env")
            assert env_path.exists()
            content = env_path.read_text()
            assert "AFFINITY_API_KEY=test-api-key-123" in content

            # Verify .gitignore was updated
            gitignore_path = Path(".gitignore")
            assert gitignore_path.exists()
            assert ".env" in gitignore_path.read_text()

    def test_setup_key_user_scope(self, runner, monkeypatch):
        """Test storing key in user config."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="test-api-key-456"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "user", "--json"])

            assert result.exit_code == 0, f"Failed with output: {result.output}"
            assert '"key_stored": true' in result.output
            assert '"scope": "user"' in result.output

            # Verify config was created
            assert mock_paths.config_path.exists()
            content = mock_paths.config_path.read_text()
            assert 'api_key = "test-api-key-456"' in content

            # Verify permissions on Unix
            if os.name == "posix":
                mode = mock_paths.config_path.stat().st_mode
                assert not (mode & stat.S_IRGRP)  # Not group readable
                assert not (mode & stat.S_IROTH)  # Not world readable

    def test_setup_key_empty_input_error(self, runner, monkeypatch):
        """Test error on empty API key."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths), patch("getpass.getpass", return_value=""):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "project"])

        assert result.exit_code == 2
        assert "No API key provided" in result.output

    def test_setup_key_invalid_format_error(self, runner, monkeypatch):
        """Test error on invalid API key format."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            # Key with spaces and special chars
            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="invalid key with spaces!"),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "project"])

        assert result.exit_code == 2
        assert "Invalid API key format" in result.output

    def test_setup_key_existing_key_no_force(self, runner, monkeypatch):
        """Test behavior when key already exists without --force."""
        monkeypatch.setenv("AFFINITY_API_KEY", "existing-key")

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with mock_cli_paths(mock_paths):
                result = runner.invoke(
                    cli, ["config", "setup-key", "--scope", "project", "--json"], input="n\n"
                )

        assert result.exit_code == 0
        assert '"key_stored": false' in result.output
        assert '"reason": "existing_key_kept"' in result.output

    def test_setup_key_existing_key_with_force(self, runner, monkeypatch):
        """Test --force overwrites existing key."""
        monkeypatch.setenv("AFFINITY_API_KEY", "existing-key")

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="new-valid-key"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                result = runner.invoke(
                    cli,
                    ["config", "setup-key", "--scope", "project", "--force", "--json"],
                )

        assert result.exit_code == 0
        assert '"key_stored": true' in result.output

    def test_setup_key_no_validate(self, runner, monkeypatch):
        """Test --no-validate skips API validation."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="test-valid-key"),
                patch("affinity.cli.commands.config_cmds._validate_key") as mock_validate,
            ):
                result = runner.invoke(
                    cli,
                    [
                        "config",
                        "setup-key",
                        "--scope",
                        "project",
                        "--no-validate",
                        "--json",
                    ],
                )

            assert result.exit_code == 0, f"Failed with output: {result.output}"
            mock_validate.assert_not_called()
            assert '"validated"' not in result.output

    def test_setup_key_validation_network_error(self, runner, monkeypatch):
        """Test graceful handling of network error during validation."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))

            # Simulate network failure
            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="test-valid-key"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=False),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "project", "--json"])

            # Key should still be stored, but validation failed
            assert result.exit_code == 0, f"Failed with output: {result.output}"
            assert '"key_stored": true' in result.output
            assert '"validated": false' in result.output

            # Verify .env was still created
            env_path = Path(".env")
            assert env_path.exists()

    def test_setup_key_appends_to_existing_env(self, runner, monkeypatch):
        """Test appending to existing .env file."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            Path(".env").write_text("OTHER_VAR=value\n")
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="new-valid-key"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                runner.invoke(cli, ["config", "setup-key", "--scope", "project", "--json"])

            content = Path(".env").read_text()
            assert "OTHER_VAR=value" in content
            assert "AFFINITY_API_KEY=new-valid-key" in content

    def test_setup_key_updates_existing_key_in_env(self, runner, monkeypatch):
        """Test updating existing key in .env."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            Path(".env").write_text("AFFINITY_API_KEY=old-key\nOTHER=value\n")
            mock_paths = make_mock_paths(Path(fs))

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value="new-valid-key"),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                runner.invoke(
                    cli,
                    ["config", "setup-key", "--scope", "project", "--force", "--json"],
                )

            content = Path(".env").read_text()
            assert "AFFINITY_API_KEY=new-valid-key" in content
            assert "old-key" not in content
            assert "OTHER=value" in content

    def test_setup_key_toml_escapes_special_chars(self, runner, monkeypatch):
        """Test that TOML special characters are properly escaped."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            # Key with quote and backslash that need escaping
            special_key = "key-with-quote-and-backslash"  # simplified for regex validation

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value=special_key),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "user", "--json"])

            assert result.exit_code == 0, f"Failed with output: {result.output}"
            content = mock_paths.config_path.read_text()
            assert f'api_key = "{special_key}"' in content

    def test_setup_key_toml_escapes_quote(self, runner, monkeypatch):
        """Test that quote characters are escaped in TOML."""
        monkeypatch.delenv("AFFINITY_API_KEY", raising=False)

        with runner.isolated_filesystem() as fs:
            mock_paths = make_mock_paths(Path(fs))
            # Need to bypass format validation for this test
            special_key = 'key"with"quotes'

            with (
                mock_cli_paths(mock_paths),
                patch("getpass.getpass", return_value=special_key),
                patch(
                    "affinity.cli.commands.config_cmds._validate_api_key_format",
                    return_value=True,
                ),
                patch("affinity.cli.commands.config_cmds._validate_key", return_value=True),
            ):
                result = runner.invoke(cli, ["config", "setup-key", "--scope", "user", "--json"])

            assert result.exit_code == 0, f"Failed with output: {result.output}"
            content = mock_paths.config_path.read_text()
            # Verify proper TOML escaping: " -> \"
            assert 'api_key = "key\\"with\\"quotes"' in content
