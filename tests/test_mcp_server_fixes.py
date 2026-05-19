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
from pathlib import Path

import pytest

from affinity.mcp.server import _builtin_filter_violation


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
