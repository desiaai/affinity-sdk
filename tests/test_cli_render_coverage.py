"""Coverage tests for affinity.cli.render.

Targets the helper functions: _humanize_title, _is_collection_envelope,
_is_collection_with_hint, _is_text_marker, _pagination_has_more,
_format_scalar_value, _is_simple_scalar_dict, _render_fields_section,
_render_human_data, _render_object_section, _extract_section_pagination.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")

from rich.console import Console

from affinity.cli.render import (
    _extract_section_pagination,
    _format_scalar_value,
    _humanize_title,
    _is_collection_envelope,
    _is_collection_with_hint,
    _is_simple_scalar_dict,
    _is_text_marker,
    _kv_table,
    _pagination_has_more,
    _render_collection_section,
    _render_collection_with_hint,
    _render_fields_section,
    _render_human_data,
    _render_object_section,
    _simple_kv_text,
    _table_from_rows,
)

# ---------------------------------------------------------------------------
# _humanize_title
# ---------------------------------------------------------------------------


class TestHumanizeTitle:
    def test_snake_case(self) -> None:
        assert _humanize_title("first_name") == "First name"

    def test_camel_case(self) -> None:
        assert _humanize_title("firstName") == "First Name"

    def test_kebab_case(self) -> None:
        assert _humanize_title("first-name") == "First name"

    def test_already_spaced(self) -> None:
        result = _humanize_title("First Name")
        assert result == "First Name"


# ---------------------------------------------------------------------------
# Type detection helpers
# ---------------------------------------------------------------------------


class TestIsCollectionEnvelope:
    def test_valid_envelope(self) -> None:
        obj = {
            "data": [{"id": 1}],
            "pagination": {"nextUrl": "https://api.example.com?page=2"},
        }
        assert _is_collection_envelope(obj) is True

    def test_missing_pagination(self) -> None:
        assert _is_collection_envelope({"data": []}) is False

    def test_missing_data(self) -> None:
        assert _is_collection_envelope({"pagination": {}}) is False

    def test_non_list_data(self) -> None:
        obj = {"data": "string", "pagination": {"nextUrl": "x"}}
        assert _is_collection_envelope(obj) is False

    def test_pagination_without_urls(self) -> None:
        obj = {"data": [], "pagination": {"total": 10}}
        assert _is_collection_envelope(obj) is False

    def test_non_dict(self) -> None:
        assert _is_collection_envelope([]) is False


class TestIsCollectionWithHint:
    def test_valid(self) -> None:
        obj = {"_rows": [{"id": 1}], "_hint": "Showing top 10"}
        assert _is_collection_with_hint(obj) is True

    def test_missing_hint(self) -> None:
        assert _is_collection_with_hint({"_rows": []}) is False

    def test_empty_hint(self) -> None:
        obj = {"_rows": [], "_hint": ""}
        assert _is_collection_with_hint(obj) is False

    def test_extra_keys(self) -> None:
        obj = {"_rows": [], "_hint": "x", "extra": True}
        assert _is_collection_with_hint(obj) is False

    def test_non_dict(self) -> None:
        assert _is_collection_with_hint("hello") is False


class TestIsTextMarker:
    def test_valid(self) -> None:
        assert _is_text_marker({"_text": "hello"}) is True

    def test_empty_text(self) -> None:
        assert _is_text_marker({"_text": ""}) is False

    def test_extra_keys(self) -> None:
        assert _is_text_marker({"_text": "x", "other": 1}) is False

    def test_non_dict(self) -> None:
        assert _is_text_marker("hello") is False


class TestPaginationHasMore:
    def test_with_next_url(self) -> None:
        assert _pagination_has_more({"nextUrl": "https://example.com"}) is True

    def test_with_next_cursor(self) -> None:
        assert _pagination_has_more({"nextCursor": "abc"}) is True

    def test_empty_values(self) -> None:
        assert _pagination_has_more({"nextUrl": ""}) is False
        assert _pagination_has_more({"nextUrl": "  "}) is False

    def test_none(self) -> None:
        assert _pagination_has_more(None) is False

    def test_no_pagination_keys(self) -> None:
        assert _pagination_has_more({"total": 10}) is False


# ---------------------------------------------------------------------------
# _format_scalar_value
# ---------------------------------------------------------------------------


class TestFormatScalarValue:
    def test_none(self) -> None:
        assert _format_scalar_value(key=None, value=None) == ""

    def test_bool(self) -> None:
        assert _format_scalar_value(key="active", value=True) == "True"

    def test_int_with_comma(self) -> None:
        assert _format_scalar_value(key="count", value=10000) == "10,000"

    def test_int_id_no_comma(self) -> None:
        assert _format_scalar_value(key="id", value=10000) == "10000"

    def test_float_integer(self) -> None:
        assert _format_scalar_value(key="score", value=42.0) == "42"

    def test_list_of_strings(self) -> None:
        result = _format_scalar_value(key="tags", value=["a", "b", "c"])
        assert result == "a, b, c"

    def test_list_of_domains(self) -> None:
        result = _format_scalar_value(key="domains", value=["example.com"])
        assert result == "https://example.com"

    def test_list_non_string(self) -> None:
        result = _format_scalar_value(key="items", value=[1, 2, 3])
        assert "3 items" in result

    def test_dict_date_range(self) -> None:
        result = _format_scalar_value(
            key="range",
            value={"start": "2024-01-01T00:00:00Z", "end": "2024-06-01T00:00:00Z"},
        )
        assert "2024-01-01" in result
        assert "2024-06-01" in result
        assert "→" in result

    def test_dict_generic(self) -> None:
        result = _format_scalar_value(key="meta", value={"a": 1, "b": 2})
        assert "2 keys" in result

    def test_string_domain(self) -> None:
        result = _format_scalar_value(key="domain", value="example.com")
        assert result == "https://example.com"

    def test_string_domain_with_scheme(self) -> None:
        result = _format_scalar_value(key="domain", value="https://example.com")
        assert result == "https://example.com"

    def test_plain_string(self) -> None:
        assert _format_scalar_value(key="name", value="Alice") == "Alice"


# ---------------------------------------------------------------------------
# _is_simple_scalar_dict
# ---------------------------------------------------------------------------


class TestIsSimpleScalarDict:
    def test_simple(self) -> None:
        assert _is_simple_scalar_dict({"a": 1, "b": "x"}) is True

    def test_with_list(self) -> None:
        assert _is_simple_scalar_dict({"a": [1]}) is False

    def test_with_nested_dict(self) -> None:
        assert _is_simple_scalar_dict({"a": {"x": 1}}) is False

    def test_with_date_range(self) -> None:
        obj = {"range": {"start": "2024-01-01", "end": "2024-12-31"}}
        assert _is_simple_scalar_dict(obj) is True


# ---------------------------------------------------------------------------
# _simple_kv_text and _kv_table
# ---------------------------------------------------------------------------


class TestSimpleKvHelpers:
    def test_simple_kv_text(self) -> None:
        text = _simple_kv_text({"name": "Alice", "age": 30})
        assert "Alice" in str(text)
        assert "30" in str(text)

    def test_kv_table(self) -> None:
        table = _kv_table({"name": "Alice", "age": 30})
        console = Console(file=io.StringIO(), force_terminal=False)
        console.print(table)
        output = console.file.getvalue()
        assert "Alice" in output
        assert "30" in output


# ---------------------------------------------------------------------------
# _render_fields_section
# ---------------------------------------------------------------------------


class TestRenderFieldsSection:
    def test_empty_fields(self) -> None:
        result = _render_fields_section(title="Fields", fields=[], field_metadata=None)
        assert result is None

    def test_single_field(self) -> None:
        fields = [{"fieldId": "field-1", "value": "Active"}]
        metadata = {"field-1": "Status"}
        result = _render_fields_section(title="Fields (1)", fields=fields, field_metadata=metadata)
        assert result is not None

    def test_multi_value_field(self) -> None:
        fields = [
            {"fieldId": "field-1", "value": "Tag1"},
            {"fieldId": "field-1", "value": "Tag2"},
        ]
        metadata = {"field-1": "Tags"}
        result = _render_fields_section(title="Fields", fields=fields, field_metadata=metadata)
        assert result is not None

    def test_verbose_includes_value_id(self) -> None:
        fields = [{"fieldId": "field-1", "value": "Active", "id": "fv-100"}]
        result = _render_fields_section(
            title="Fields",
            fields=fields,
            field_metadata={"field-1": "Status"},
            verbose=True,
        )
        assert result is not None

    def test_dict_value_with_data(self) -> None:
        fields = [{"fieldId": "field-1", "value": {"type": "text", "data": "hello"}}]
        result = _render_fields_section(
            title="Fields",
            fields=fields,
            field_metadata=None,
        )
        assert result is not None

    def test_list_value_with_names(self) -> None:
        fields = [
            {
                "fieldId": "field-1",
                "value": [{"name": "Alice"}, {"name": "Bob"}],
            }
        ]
        result = _render_fields_section(
            title="Fields",
            fields=fields,
            field_metadata=None,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# _extract_section_pagination
# ---------------------------------------------------------------------------


class TestExtractSectionPagination:
    def test_keyed_pagination(self) -> None:
        result = _extract_section_pagination(
            meta_pagination={"entries": {"nextUrl": "x"}},
            section="entries",
        )
        assert result == {"nextUrl": "x"}

    def test_legacy_unkeyed(self) -> None:
        result = _extract_section_pagination(
            meta_pagination={"nextUrl": "x"},
            section="entries",
        )
        assert result == {"nextUrl": "x"}

    def test_none_pagination(self) -> None:
        result = _extract_section_pagination(meta_pagination=None, section="entries")
        assert result is None

    def test_no_match(self) -> None:
        result = _extract_section_pagination(
            meta_pagination={"total": 10},
            section="entries",
        )
        assert result is None


# ---------------------------------------------------------------------------
# _render_human_data
# ---------------------------------------------------------------------------


class TestRenderHumanData:
    def test_list_of_dicts(self) -> None:
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_list_of_dicts_with_pagination(self) -> None:
        data = [{"id": 1}]
        result = _render_human_data(
            data=data,
            meta_pagination={"nextUrl": "https://api.example.com?page=2"},
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_single_dict_object(self) -> None:
        data = {"person": {"id": 1, "name": "Alice", "email": "a@b.com"}}
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_collection_envelope(self) -> None:
        data = {
            "data": [{"id": 1}],
            "pagination": {"nextUrl": "https://api.example.com"},
        }
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_text_marker(self) -> None:
        data = {"info": {"_text": "No results found."}}
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_collection_with_hint(self) -> None:
        data = {
            "results": {
                "_rows": [{"id": 1}],
                "_hint": "Showing top results",
            }
        }
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_multi_section_dict(self) -> None:
        data = {
            "info": {"_text": "Header text"},
            "entries": [{"id": 1, "name": "A"}],
            "details": {"key": "val"},
        }
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_empty_list(self) -> None:
        result = _render_human_data(
            data=[],
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_scalar_value(self) -> None:
        result = _render_human_data(
            data="some string",
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_none_data(self) -> None:
        result = _render_human_data(
            data=None,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None

    def test_dict_with_scalar_value_key(self) -> None:
        data = {"status": "active", "count": 42}
        result = _render_human_data(
            data=data,
            meta_pagination=None,
            meta_resolved=None,
            verbosity=0,
        )
        assert result is not None


# ---------------------------------------------------------------------------
# _table_from_rows
# ---------------------------------------------------------------------------


class TestTableFromRows:
    def test_basic(self) -> None:
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        _table, omitted = _table_from_rows(rows)
        assert omitted == 0

    def test_empty_rows(self) -> None:
        _table, omitted = _table_from_rows([])
        assert omitted == 0

    def test_column_limiting(self) -> None:
        rows = [{"c" + str(i): i for i in range(50)}]
        _table, omitted = _table_from_rows(rows, max_columns=5)
        assert omitted > 0

    def test_all_columns(self) -> None:
        rows = [{"c" + str(i): i for i in range(50)}]
        _table, omitted = _table_from_rows(rows, all_columns=True)
        assert omitted == 0


# ---------------------------------------------------------------------------
# _render_collection_section
# ---------------------------------------------------------------------------


class TestRenderCollectionSection:
    def test_basic(self) -> None:
        result = _render_collection_section(
            title="Items",
            rows=[{"id": 1, "name": "A"}],
            pagination=None,
        )
        assert result is not None

    def test_with_pagination(self) -> None:
        result = _render_collection_section(
            title="Items",
            rows=[{"id": 1}],
            pagination={"nextUrl": "https://api.example.com"},
        )
        assert result is not None

    def test_empty_rows(self) -> None:
        result = _render_collection_section(title="Items", rows=[], pagination=None)
        assert result is not None


class TestRenderCollectionWithHint:
    def test_basic(self) -> None:
        result = _render_collection_with_hint(
            title="Results",
            rows=[{"id": 1}],
            hint="Showing top results",
        )
        assert result is not None


# ---------------------------------------------------------------------------
# _render_object_section
# ---------------------------------------------------------------------------


class TestRenderObjectSection:
    def test_simple_scalars(self) -> None:
        result = _render_object_section(
            title="person",
            obj={"id": 1, "name": "Alice", "email": "a@b.com"},
            verbosity=0,
            pagination=None,
        )
        assert result is not None

    def test_nested_dict(self) -> None:
        result = _render_object_section(
            title="company",
            obj={"id": 1, "name": "Acme", "address": {"city": "NYC"}},
            verbosity=0,
            pagination=None,
        )
        assert result is not None

    def test_with_list_sub_section(self) -> None:
        result = _render_object_section(
            title="person",
            obj={
                "id": 1,
                "emails": [{"email": "a@b.com"}],
            },
            verbosity=0,
            pagination=None,
        )
        assert result is not None
