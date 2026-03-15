from __future__ import annotations

import io
import re

from rich.console import Console

from affinity.cli.render import _table_from_rows


def _render_table_text(table: object, width: int = 220) -> str:
    """Render a Rich table to plain text with whitespace normalised.

    Box-drawing characters are stripped so assertions work even when
    content word-wraps across table rows.
    """
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=width,
    )
    raw = "\n".join(
        "".join(seg.text for seg in line)
        for line in console.render_lines(table, options=console.options)
    )
    stripped = re.sub(r"[━┏┓┗┛┃┡┩╇┳┻╋─│┌┐└┘├┤┬┴┼╈╉╊]+", " ", raw)
    return " ".join(stripped.split())


def test_table_from_rows_humanizes_typed_person_value() -> None:
    table, _ = _table_from_rows(
        [
            {
                "id": "source-of-introduction",
                "value": {
                    "type": "person",
                    "data": {
                        "id": 42,
                        "firstName": "Ada",
                        "lastName": "Lovelace",
                        "primaryEmailAddress": "ada@example.com",
                        "type": "person",
                    },
                },
            }
        ]
    )
    rendered = _render_table_text(table)
    assert "Ada Lovelace" in rendered
    assert "<ada@example.com>" in rendered
    assert "(id=42)" in rendered


def test_table_from_rows_humanizes_typed_interaction_value() -> None:
    table, _ = _table_from_rows(
        [
            {
                "id": "first-email",
                "value": {
                    "type": "interaction",
                    "data": {
                        "id": 1001,
                        "type": "email",
                        "sentAt": "2025-01-02T03:04:05Z",
                        "subject": "Hello there",
                        "from": [],
                        "to": [],
                        "cc": [],
                    },
                },
            }
        ]
    )
    rendered = _render_table_text(table)
    assert "email" in rendered
    assert "2025-01-02 03:04:05" in rendered
    assert "Hello there" in rendered
    assert "(id=1001)" in rendered


def test_table_from_rows_formats_quantity_but_not_ids() -> None:
    table, _ = _table_from_rows([{"id": 1234567, "count": 1234567}])
    rendered = _render_table_text(table, width=120)
    assert "1234567" in rendered
    assert "1,234,567" in rendered


def test_table_from_rows_formats_money_with_currency_from_name() -> None:
    table, _ = _table_from_rows(
        [
            {
                "name": "Total Funding Amount (EUR)",
                "value": {"type": "number", "data": 310000.0},
            }
        ]
    )
    rendered = _render_table_text(table, width=200)
    assert "€310,000" in rendered


def test_table_from_rows_formats_year_without_thousands_separator() -> None:
    table, _ = _table_from_rows(
        [{"name": "Year Founded", "value": {"type": "number", "data": 2019.0}}]
    )
    rendered = _render_table_text(table, width=120)
    assert "2019" in rendered
    assert "2,019" not in rendered


def test_table_from_rows_humanizes_dropdown_multi_from_dict_items() -> None:
    table, _ = _table_from_rows(
        [
            {
                "name": "Reason for Passing",
                "value": {
                    "type": "dropdown-multi",
                    "data": [{"dropdownOptionId": 1, "text": "Not a fit"}],
                },
            }
        ]
    )
    rendered = _render_table_text(table, width=120)
    assert "Not a fit" in rendered
    assert "object" not in rendered
