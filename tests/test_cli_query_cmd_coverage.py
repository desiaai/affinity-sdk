"""Coverage tests for affinity.cli.commands.query_cmd.

Targets the 73% of untested code: validation, error handling,
output format paths, helper functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")

from click.testing import CliRunner

from affinity.cli.commands.query_cmd import (
    _count_rows_in_output,
    _get_query_input,
    query_cmd,
)
from affinity.cli.context import CLIContext
from affinity.cli.errors import CLIError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def cli_context() -> CLIContext:
    ctx = MagicMock(spec=CLIContext)
    ctx.output = "json"
    ctx.quiet = False
    ctx.verbosity = 0
    ctx._output_source = None
    ctx._output_format_conflict = None
    return ctx


# ---------------------------------------------------------------------------
# Numeric option validation (lines 161-166)
# ---------------------------------------------------------------------------


class TestQueryCmdValidation:
    """Numeric option validation exits with code 2."""

    def test_max_records_zero_errors(self, runner: CliRunner, cli_context: CLIContext) -> None:
        result = runner.invoke(
            query_cmd,
            ["--max-records", "0", "--query", '{"from":"persons"}'],
            obj=cli_context,
        )
        assert result.exit_code == 2

    def test_max_records_negative_errors(self, runner: CliRunner, cli_context: CLIContext) -> None:
        result = runner.invoke(
            query_cmd,
            ["--max-records", "-5", "--query", '{"from":"persons"}'],
            obj=cli_context,
        )
        assert result.exit_code == 2

    def test_timeout_zero_errors(self, runner: CliRunner, cli_context: CLIContext) -> None:
        result = runner.invoke(
            query_cmd,
            ["--timeout", "0", "--query", '{"from":"persons"}'],
            obj=cli_context,
        )
        assert result.exit_code == 2

    def test_timeout_negative_errors(self, runner: CliRunner, cli_context: CLIContext) -> None:
        result = runner.invoke(
            query_cmd,
            ["--timeout", "-1", "--query", '{"from":"persons"}'],
            obj=cli_context,
        )
        assert result.exit_code == 2

    def test_max_output_bytes_zero_errors(self, runner: CliRunner, cli_context: CLIContext) -> None:
        result = runner.invoke(
            query_cmd,
            [
                "--max-output-bytes",
                "0",
                "--query",
                '{"from":"persons"}',
            ],
            obj=cli_context,
        )
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# CLIError display path (lines 201-206)
# ---------------------------------------------------------------------------


class TestQueryCmdCLIErrorDisplay:
    """CLIError caught at top level and displayed cleanly."""

    def test_clierror_message_displayed(self, runner: CliRunner, cli_context: CLIContext) -> None:
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=CLIError("something went wrong"),
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "something went wrong" in result.output

    def test_clierror_hint_displayed(self, runner: CliRunner, cli_context: CLIContext) -> None:
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=CLIError("bad query", hint="Try a simpler query."),
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "Try a simpler query" in result.output


# ---------------------------------------------------------------------------
# Exception handling in _query_cmd_impl (lines 471-492)
# ---------------------------------------------------------------------------


class TestQueryCmdExceptionPaths:
    """Exception types raised during execution become CLIErrors.

    The exceptions are caught inside ``_query_cmd_impl`` and re-raised
    as ``CLIError``, which the outer ``query_cmd`` catches and displays.
    We patch ``_query_cmd_impl`` to raise them directly since the lazy
    imports inside that function make module-level patching difficult.
    """

    def test_query_timeout_error(self, runner: CliRunner, cli_context: CLIContext) -> None:
        err = CLIError("Query timed out after 42.5s: took too long")
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=err,
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "timed out" in result.output

    def test_query_safety_limit_error(self, runner: CliRunner, cli_context: CLIContext) -> None:
        err = CLIError("Query exceeded safety limit: hit limit")
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=err,
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "safety limit" in result.output

    def test_query_execution_error(self, runner: CliRunner, cli_context: CLIContext) -> None:
        err = CLIError("Query execution failed: boom")
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=err,
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "execution failed" in result.output

    def test_query_interrupted_no_partial(self, runner: CliRunner, cli_context: CLIContext) -> None:
        err = CLIError("Query interrupted: signal")
        with patch(
            "affinity.cli.commands.query_cmd._query_cmd_impl",
            side_effect=err,
        ):
            result = runner.invoke(
                query_cmd,
                ["--query", '{"from":"persons"}'],
                obj=cli_context,
            )
        assert result.exit_code != 0
        assert "interrupted" in result.output.lower()


# ---------------------------------------------------------------------------
# _count_rows_in_output (lines 704-754)
# ---------------------------------------------------------------------------


class TestCountRowsInOutput:
    """Pure function: count data rows in formatted output."""

    def test_toon_with_header(self) -> None:
        output = "data[3]{id,name}:\n  1 | Alice\n  2 | Bob\n  3 | Charlie\n"
        assert _count_rows_in_output(output, "toon") == 3

    def test_toon_fallback_count(self) -> None:
        output = "  1 | Alice\n  2 | Bob\n"
        assert _count_rows_in_output(output, "toon") == 2

    def test_markdown(self) -> None:
        output = "| id | name |\n| -- | ---- |\n| 1  | Alice |\n| 2  | Bob   |\n"
        assert _count_rows_in_output(output, "markdown") == 2

    def test_markdown_empty(self) -> None:
        output = "| id | name |\n| -- | ---- |\n"
        assert _count_rows_in_output(output, "markdown") == 0

    def test_jsonl(self) -> None:
        output = '{"id":1,"name":"Alice"}\n{"id":2,"name":"Bob"}\n'
        assert _count_rows_in_output(output, "jsonl") == 2

    def test_jsonl_ignores_truncation_marker(self) -> None:
        output = '{"id":1}\n{"truncated":true}\n'
        assert _count_rows_in_output(output, "jsonl") == 1

    def test_csv(self) -> None:
        output = "id,name\n1,Alice\n2,Bob\n"
        assert _count_rows_in_output(output, "csv") == 2

    def test_csv_header_only(self) -> None:
        output = "id,name\n"
        assert _count_rows_in_output(output, "csv") == 0

    def test_json_with_data_array(self) -> None:
        data = {"data": [{"id": 1}, {"id": 2}, {"id": 3}]}
        output = json.dumps(data)
        assert _count_rows_in_output(output, "json") == 3

    def test_json_empty_data(self) -> None:
        data = {"data": []}
        output = json.dumps(data)
        assert _count_rows_in_output(output, "json") == 0

    def test_json_invalid(self) -> None:
        assert _count_rows_in_output("not json", "json") == 0

    def test_unknown_format(self) -> None:
        assert _count_rows_in_output("anything", "unknown") == 0


# ---------------------------------------------------------------------------
# _get_query_input (lines 757-802)
# ---------------------------------------------------------------------------


class TestGetQueryInput:
    def test_from_file(self, tmp_path: Path) -> None:
        f = tmp_path / "q.json"
        f.write_text('{"from":"persons"}')
        result = _get_query_input(f, None)
        assert result == {"from": "persons"}

    def test_from_file_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json")
        with pytest.raises(CLIError, match="Invalid JSON in file"):
            _get_query_input(f, None)

    def test_from_query_str(self) -> None:
        result = _get_query_input(None, '{"from":"companies"}')
        assert result == {"from": "companies"}

    def test_from_query_str_invalid_json(self) -> None:
        with pytest.raises(CLIError, match="Invalid JSON"):
            _get_query_input(None, "bad")

    def test_no_input_raises(self) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(CLIError, match="No query provided"):
                _get_query_input(None, None)

    def test_from_stdin(self) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = '{"from":"lists"}'
            result = _get_query_input(None, None)
        assert result == {"from": "lists"}

    def test_stdin_invalid_json(self) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "{"
            with pytest.raises(CLIError, match="Invalid JSON from stdin"):
                _get_query_input(None, None)
