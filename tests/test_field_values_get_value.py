"""
Tests for FieldValues.get_value() method.
"""

from __future__ import annotations

import pytest

from affinity.models.entities import Company


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
        """get_value() should extract dropdown option ID."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"dropdownOptionId": 123}}],
            }
        )
        assert company.fields.get_value("field-1") == 123

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
