"""
Tests for FieldValues.get_value() method.
"""

from __future__ import annotations

import pytest

from affinity.models.entities import Company, DropdownOption
from affinity.models.types import DropdownOptionId


@pytest.mark.req("SDK-FIELD-VALUE-EXTRACTION")
class TestFieldValuesGetValue:
    """Tests for FieldValues.get_value() method."""

    def test_get_value_text_field(self) -> None:
        """get_value() should extract text field data."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"data": "Active"}}],
            }
        )
        assert company.fields.get_value("field-1") == "Active"

    def test_get_value_dropdown_field(self) -> None:
        """get_value() should return DropdownOption for dropdown values."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"dropdownOptionId": 123}}],
            }
        )
        result = company.fields.get_value("field-1")
        assert isinstance(result, DropdownOption)
        assert result.id == DropdownOptionId(123)
        assert result.text == ""  # no text in ID-only data

    def test_get_value_dropdown_wrapped_in_data(self) -> None:
        """get_value() should recurse through data envelope for dropdown."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [
                    {
                        "id": "field-1",
                        "value": {"type": "dropdown", "data": {"dropdownOptionId": 42}},
                    }
                ],
            }
        )
        result = company.fields.get_value("field-1")
        assert isinstance(result, DropdownOption)
        assert result.id == DropdownOptionId(42)

    def test_get_value_ranked_dropdown_wrapped_in_data(self) -> None:
        """get_value() should return DropdownOption for ranked-dropdown."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [
                    {
                        "id": "field-1",
                        "value": {
                            "type": "ranked-dropdown",
                            "data": {
                                "dropdownOptionId": 7,
                                "text": "Passed",
                                "rank": 8,
                                "color": "green",
                            },
                        },
                    }
                ],
            }
        )
        result = company.fields.get_value("field-1")
        assert isinstance(result, DropdownOption)
        assert result.id == DropdownOptionId(7)
        assert result.text == "Passed"
        assert result.rank == 8
        assert result.color == "green"

    def test_get_value_dropdown_multi_wrapped_in_data(self) -> None:
        """get_value() should return list of DropdownOption for dropdown-multi."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [
                    {
                        "id": "field-1",
                        "value": {
                            "type": "dropdown-multi",
                            "data": [
                                {"dropdownOptionId": 1, "text": "A"},
                                {"dropdownOptionId": 2, "text": "B"},
                            ],
                        },
                    }
                ],
            }
        )
        result = company.fields.get_value("field-1")
        assert len(result) == 2
        assert all(isinstance(opt, DropdownOption) for opt in result)
        assert result[0].text == "A"
        assert result[1].text == "B"

    def test_get_value_multi_value(self) -> None:
        """get_value() should extract list of values."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": [{"data": "a"}, {"data": "b"}]}],
            }
        )
        assert company.fields.get_value("field-1") == ["a", "b"]

    def test_get_value_missing_field(self) -> None:
        """get_value() should return None for missing field."""
        company = Company.model_validate({"id": 1, "name": "Test", "fields": []})
        assert company.fields.get_value("field-999") is None

    def test_get_value_null_value(self) -> None:
        """get_value() should return None for null value."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": None}],
            }
        )
        assert company.fields.get_value("field-1") is None

    def test_get_value_location_dict(self) -> None:
        """get_value() should return location dict as-is when no data/dropdown key."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"city": "SF", "state": "CA"}}],
            }
        )
        assert company.fields.get_value("field-1") == {"city": "SF", "state": "CA"}

    def test_get_value_with_typed_field_id(self) -> None:
        """get_value() should accept typed FieldId."""
        from affinity.types import FieldId

        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"data": "Active"}}],
            }
        )
        assert company.fields.get_value(FieldId(1)) == "Active"
