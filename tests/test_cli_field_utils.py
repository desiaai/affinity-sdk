"""Tests for CLI field utility functions."""

from __future__ import annotations

import pytest

from affinity.cli.field_utils import FieldResolver as CLIFieldResolver
from affinity.models.entities import DropdownOption, FieldMetadata
from affinity.models.types import DropdownOptionId, FieldId, FieldValueType


@pytest.fixture
def dropdown_multi_resolver() -> CLIFieldResolver:
    """Create a CLI FieldResolver with dropdown-multi field metadata."""
    fields = [
        FieldMetadata(
            id=FieldId(2166604),
            name="Sourced by",
            value_type=FieldValueType.DROPDOWN_MULTI,
            dropdown_options=[
                DropdownOption(id=DropdownOptionId(5064548), text="YG"),
                DropdownOption(id=DropdownOptionId(5064549), text="AB"),
            ],
        ),
        FieldMetadata(
            id=FieldId(100),
            name="Status",
            value_type=FieldValueType.DROPDOWN,
            dropdown_options=[
                DropdownOption(id=DropdownOptionId(200), text="Active"),
                DropdownOption(id=DropdownOptionId(201), text="Closed"),
            ],
        ),
        FieldMetadata(
            id=FieldId(300),
            name="Notes",
            value_type=FieldValueType.TEXT,
        ),
    ]
    return CLIFieldResolver(fields)


@pytest.mark.req("CLI-DROPDOWN-MULTI-FIX")
class TestResolveDropdownValue:
    """Tests for resolve_dropdown_value with dropdown-multi fields."""

    def test_dropdown_multi_resolves_text_to_array(
        self, dropdown_multi_resolver: CLIFieldResolver
    ) -> None:
        """dropdown-multi should resolve text to array of option objects."""
        value, type_str = dropdown_multi_resolver.resolve_dropdown_value("field-2166604", "YG")
        assert type_str == "dropdown-multi"
        assert value == [{"dropdownOptionId": 5064548}]

    def test_dropdown_multi_resolves_id_to_array(
        self, dropdown_multi_resolver: CLIFieldResolver
    ) -> None:
        """dropdown-multi should resolve numeric ID to array of option objects."""
        value, type_str = dropdown_multi_resolver.resolve_dropdown_value("field-2166604", "5064548")
        assert type_str == "dropdown-multi"
        assert value == [{"dropdownOptionId": 5064548}]

    def test_dropdown_multi_case_insensitive(
        self, dropdown_multi_resolver: CLIFieldResolver
    ) -> None:
        """dropdown-multi should resolve case-insensitively."""
        value, _type_str = dropdown_multi_resolver.resolve_dropdown_value("field-2166604", "yg")
        assert value == [{"dropdownOptionId": 5064548}]

    def test_dropdown_multi_invalid_option_raises(
        self, dropdown_multi_resolver: CLIFieldResolver
    ) -> None:
        """dropdown-multi should raise CLIError for unknown option text."""
        from affinity.cli.errors import CLIError

        with pytest.raises(CLIError, match="not found"):
            dropdown_multi_resolver.resolve_dropdown_value("field-2166604", "Unknown")

    def test_regular_dropdown_returns_single_object(
        self, dropdown_multi_resolver: CLIFieldResolver
    ) -> None:
        """Regular dropdown should still return single object (not array)."""
        value, type_str = dropdown_multi_resolver.resolve_dropdown_value("field-100", "Active")
        assert type_str == "dropdown"
        assert value == {"dropdownOptionId": 200}

    def test_text_field_returns_unchanged(self, dropdown_multi_resolver: CLIFieldResolver) -> None:
        """Non-dropdown fields should return value unchanged."""
        value, type_str = dropdown_multi_resolver.resolve_dropdown_value("field-300", "some text")
        assert type_str == "text"
        assert value == "some text"
