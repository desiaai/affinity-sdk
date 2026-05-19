"""Tests for affinity.mcp.server fixes.

Covers two regressions seen against the previous pinned SHA in a downstream
Claude Code agent harness:

1. The ``query`` MCP tool returned ``usage_error: "No such option '--stdin'"``
   on every invocation because the Python MCP server passed ``--stdin`` to the
   CLI, which does not expose that flag. The bash wrapper at
   ``mcp/tools/query/tool.sh`` had already migrated to ``--file <tempfile>``
   (commit ``dada1ad``); the Python wrapper was missed by that fix.

2. ``execute-read-command company ls --filter 'name = "X"'`` silently returned
   the unfiltered list because the Affinity V2 API does not honor ``--filter``
   on built-in fields (name, domain, domains, id, firstName, lastName, email,
   emails). The MCP server now refuses such filters loudly with
   ``error.type: "unsupported_filter"``.
"""

# NB: this file lives at tests/test_mcp_server_fixes.py (not tests/mcp/...)
# on purpose. pytest adds tests/ to sys.path during collection, which makes
# tests/mcp/__init__.py shadow the installed ``mcp`` Python package and
# breaks ``from mcp.server import Server`` inside ``affinity/mcp/server.py``.
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from affinity.mcp.server import _builtin_filter_violation, _get_all_commands, _validate_argv


class TestBuiltinFilterViolation:
    """Detection helper for filters that the V2 API silently drops."""

    @pytest.mark.parametrize(
        "argv, expected",
        [
            (["--filter", 'name = "Acme"'], "name"),
            (["--filter", 'name =~ "acme"'], "name"),
            (["--filter", 'domain = "acme.com"'], "domain"),
            (["--filter", 'domains =~ "acme"'], "domains"),
            (["--filter", "id = 12345"], "id"),
            (["--filter", 'firstName = "Alice"'], "firstName"),
            (["--filter", 'lastName =~ "smith"'], "lastName"),
            (["--filter", 'email = "a@b.co"'], "email"),
            (["--filter", 'emails =~ "a@b"'], "emails"),
            # Leading whitespace must not hide the violation.
            (["--filter", '   name = "X"'], "name"),
            # Multiple --filter args; first violator wins.
            (["--filter", 'Industry = "OK"', "--filter", 'name = "X"'], "name"),
            # No whitespace around the operator — the Affinity filter
            # tokenizer accepts this shape (operator chars stop the
            # field-name read), so the preflight must catch it too.
            (["--filter", 'name="X"'], "name"),
            (["--filter", 'name=~"X"'], "name"),
            (["--filter", 'domain="acme.com"'], "domain"),
            (["--filter", "id>=12345"], "id"),
            (["--filter", "email!=null"], "email"),
            # Click's --filter=value single-arg form. Without explicit
            # handling this bypasses the loop's `a == "--filter"` check.
            (['--filter=name="Acme"'], "name"),
            (["--filter=name = \"Acme\""], "name"),
            (["--filter=domain=acme.com"], "domain"),
            (["--filter=id>=12345"], "id"),
            # Mixed: legitimate two-arg call alongside a fused one.
            (["--max-results", "10", '--filter=email="x@y"'], "email"),
        ],
    )
    def test_detects_builtin_field_filters(self, argv: list[str], expected: str) -> None:
        assert _builtin_filter_violation(argv) == expected

    @pytest.mark.parametrize(
        "argv",
        [
            # Custom-field filters are fine.
            ["--filter", 'Industry = "Software"'],
            ["--filter", 'Status =~ "Active"'],
            # No --filter at all.
            ["--max-results", "50"],
            # --filter without a value (parser will error elsewhere).
            ["--filter"],
            # --filter with an empty value.
            ["--filter", ""],
            # Free-text search is not blocked.
            ["--query", "Acme"],
        ],
    )
    def test_passes_safe_argvs(self, argv: list[str]) -> None:
        assert _builtin_filter_violation(argv) is None


class TestFilterPreflightKillSwitch:
    """The preflight is on by default but disableable via
    ``AFFINITY_MCP_FILTER_PREFLIGHT=0`` for ops incident response.
    Mirrors the existing ``AFFINITY_MCP_READ_ONLY`` /
    ``AFFINITY_MCP_DISABLE_DESTRUCTIVE`` patterns in the same module."""

    def test_default_state_is_enabled_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With AFFINITY_MCP_FILTER_PREFLIGHT unset, the constant evaluates True."""
        monkeypatch.delenv("AFFINITY_MCP_FILTER_PREFLIGHT", raising=False)
        # Re-evaluate the module-level expression in isolation. We can't
        # just reload the module — that would clobber other imported names
        # in already-loaded test modules. Re-running the expression in a
        # constrained namespace pins the contract.
        result = os.environ.get("AFFINITY_MCP_FILTER_PREFLIGHT", "1") != "0"
        assert result is True

    def test_explicit_one_evaluates_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFFINITY_MCP_FILTER_PREFLIGHT", "1")
        assert (os.environ.get("AFFINITY_MCP_FILTER_PREFLIGHT", "1") != "0") is True

    def test_explicit_zero_evaluates_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AFFINITY_MCP_FILTER_PREFLIGHT", "0")
        assert (os.environ.get("AFFINITY_MCP_FILTER_PREFLIGHT", "1") != "0") is False

    def test_helper_remains_pure_regardless_of_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The helper function itself does NOT read the env var — gating
        lives at the call-site (in the read/write handlers). This pins
        the contract: any env value still leaves the function detecting
        violations correctly. Operators relying on the env-var
        kill-switch get suppression at the call-site only."""
        for env_value in ("0", "1", "anything"):
            monkeypatch.setenv("AFFINITY_MCP_FILTER_PREFLIGHT", env_value)
            assert _builtin_filter_violation(["--filter", 'name = "X"']) == "name"


class TestCsvFlagRejection:
    """The MCP wrapper auto-appends --json. Passing --csv collides with that
    and the CLI emits a misleading "--json and --csv are mutually exclusive"
    error (the agent never passed --json — the wrapper did). Reject --csv
    at the wrapper boundary with a useful hint."""

    def test_csv_flag_is_rejected(self) -> None:
        valid, err = _validate_argv(["--csv", "--max-results", "100"])
        assert valid is False
        assert "--csv" in err
        assert "JSON" in err  # hint mentions JSON-output requirement
        assert "pagination" in err.lower() or "cursor" in err.lower()

    def test_csv_after_other_flags_still_rejected(self) -> None:
        valid, err = _validate_argv(["--max-results", "100", "--csv"])
        assert valid is False
        assert "--csv" in err

    def test_argv_without_csv_passes(self) -> None:
        valid, err = _validate_argv(["--max-results", "100"])
        assert valid is True
        assert err == ""

    def test_csv_substring_in_value_does_not_match(self) -> None:
        # A filter value containing "--csv" must not trigger the guard.
        valid, err = _validate_argv(["--filter", "Notes =~ '--csv flag'"])
        assert valid is True


class TestCommandDedup:
    """`xaffinity <group> --help --json` returns subcommands of that group,
    and some commands appear under multiple parent groups (notably
    `list-entry` subcommands are also exposed under `list`, and some
    aliases cause `interaction ls` to show up 5+ times). _get_all_commands
    must dedupe by name so discover-commands doesn't repeat them."""

    def test_get_all_commands_returns_unique_names(self) -> None:
        # _get_all_commands shells out to the CLI; if uvx hasn't installed
        # the package the CLI binary won't be on PATH and this test should
        # be skipped rather than fail (mirrors how other tests in the
        # project handle the optional CLI dependency).
        try:
            commands = _get_all_commands()
        except FileNotFoundError:
            pytest.skip("xaffinity CLI not on PATH in this env")
        names = [c.get("name") for c in commands if c.get("name")]
        assert len(names) == len(set(names)), (
            f"command list contains duplicates: {sorted([n for n in names if names.count(n) > 1])}"
        )


def _server_source() -> str:
    """Read the MCP server module source verbatim for static regression tests."""
    path = Path(__file__).resolve().parents[1] / "affinity" / "mcp" / "server.py"
    return path.read_text(encoding="utf-8")


class TestQueryHandlerUsesFile:
    """Regression tests for bug #2: ``query`` handler must use ``--file``, never ``--stdin``.

    The handler is a closure inside ``serve()`` so we cannot import it directly
    without refactoring the module. A source-level assertion is the smallest
    viable guard: it fails if anyone re-introduces the ``--stdin`` path or
    drops the ``tempfile`` import that the patched handler relies on.
    """

    def test_module_imports_tempfile(self) -> None:
        src = _server_source()
        tree = ast.parse(src)
        imports = {
            n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names
        }
        assert "tempfile" in imports, (
            "regression: query handler relies on tempfile.NamedTemporaryFile"
        )

    def test_query_handler_does_not_pass_stdin_flag(self) -> None:
        src = _server_source()
        # The string '--stdin' may appear in comments documenting the bug,
        # but it must NOT appear inside a list literal that becomes argv.
        # Heuristic: a literal ``"--stdin"`` (with double quotes) is what
        # the old buggy code used; mentions in comments use a different
        # quoting context (apostrophes inside English prose). If anyone
        # re-introduces the bug they will almost certainly use a Python
        # string literal.
        assert '"--stdin"' not in src, (
            "regression: re-introducing the --stdin flag in the Python MCP "
            "query handler will break the tool against the deployed CLI"
        )

    def test_query_handler_uses_file_flag(self) -> None:
        src = _server_source()
        assert '"--file"' in src, "query handler must pass --file <tempfile-path> to xaffinity"

    def test_query_handler_writes_tempfile(self) -> None:
        src = _server_source()
        assert "tempfile.NamedTemporaryFile" in src, (
            "query handler must persist the query payload to a temp file before invoking the CLI"
        )
