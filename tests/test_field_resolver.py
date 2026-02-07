"""
Tests for FieldResolver helper class.
"""

from __future__ import annotations

import pytest

from affinity.field_resolver import FieldResolver
from affinity.models.entities import Company, DropdownOption, FieldMetadata
from affinity.models.types import DropdownOptionId, FieldId, FieldValueType


@pytest.mark.req("SDK-FIELD-RESOLVER")
class TestFieldResolver:
    """Tests for FieldResolver helper."""

    @pytest.fixture
    def resolver(self):
        """Create resolver with sample field metadata."""
        fields = [
            FieldMetadata(id=FieldId(1), name="Status", value_type=FieldValueType.TEXT),
            FieldMetadata(
                id=FieldId(2),
                name="Stage",
                value_type=FieldValueType.DROPDOWN,
                dropdown_options=[
                    DropdownOption(id=DropdownOptionId(100), text="Lead"),
                    DropdownOption(id=DropdownOptionId(101), text="Negotiation"),
                ],
            ),
        ]
        return FieldResolver(fields)

    def test_get_by_name(self, resolver) -> None:
        """get() should find field by name and extract value."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"data": "Active"}}],
            }
        )
        assert resolver.get(company, "Status") == "Active"

    def test_get_case_insensitive(self, resolver) -> None:
        """get() should be case-insensitive for field names."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"data": "Active"}}],
            }
        )
        assert resolver.get(company, "STATUS") == "Active"
        assert resolver.get(company, "status") == "Active"

    def test_get_resolve_dropdowns(self, resolver) -> None:
        """get(resolve_dropdowns=True) should return option text."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-2", "value": {"dropdownOptionId": 101}}],
            }
        )
        assert resolver.get(company, "Stage") == 101
        assert resolver.get(company, "Stage", resolve_dropdowns=True) == "Negotiation"

    def test_get_many(self, resolver) -> None:
        """get_many() should extract multiple fields."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [
                    {"id": "field-1", "value": {"data": "Active"}},
                    {"id": "field-2", "value": {"dropdownOptionId": 100}},
                ],
            }
        )
        values = resolver.get_many(company, ["Status", "Stage", "Missing"])
        assert values == {"Status": "Active", "Stage": 100, "Missing": None}

    def test_get_warns_when_fields_not_requested(self, resolver) -> None:
        """get() should emit UserWarning when entity.fields.requested is False."""
        company = Company.model_validate({"id": 1, "name": "Test"})
        assert not company.fields.requested

        with pytest.warns(UserWarning, match="Fields were not requested"):
            result = resolver.get(company, "Status")
        assert result is None

    def test_has_field(self, resolver) -> None:
        """has_field() should check field existence case-insensitively."""
        assert resolver.has_field("Status") is True
        assert resolver.has_field("status") is True
        assert resolver.has_field("Nonexistent") is False

    def test_field_names(self, resolver) -> None:
        """field_names() should return all available names."""
        names = resolver.field_names()
        assert "Status" in names
        assert "Stage" in names
        assert len(names) == 2

    def test_get_by_id(self, resolver) -> None:
        """get_by_id() should access field value by ID directly."""
        company = Company.model_validate(
            {
                "id": 1,
                "name": "Test",
                "fields": [{"id": "field-1", "value": {"data": "Active"}}],
            }
        )
        assert resolver.get_by_id(company, FieldId(1)) == "Active"

    def test_duplicate_field_name_warns(self) -> None:
        """FieldResolver should warn on duplicate field names."""
        fields = [
            FieldMetadata(id=FieldId(1), name="Status", value_type=FieldValueType.TEXT),
            FieldMetadata(id=FieldId(2), name="Status", value_type=FieldValueType.TEXT),
        ]
        with pytest.warns(UserWarning, match="Duplicate field name"):
            FieldResolver(fields)

    def test_get_delegates_to_list_entry_entity(self, resolver) -> None:
        """get() should delegate to entry.entity when entry.fields not requested."""
        import warnings as _warnings

        from affinity.models.entities import ListEntryWithEntity

        entry = ListEntryWithEntity.model_validate(
            {
                "id": 1,
                "listId": 100,
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "company",
                "entity": {
                    "id": 1,
                    "name": "Test Co",
                    "fields": [{"id": "field-1", "value": {"data": "Active"}}],
                },
            }
        )
        assert not entry.fields.requested
        assert entry.entity.fields.requested

        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            result = resolver.get(entry, "Status")
        assert result == "Active"
        assert not any("Fields were not requested" in str(x.message) for x in w)

    def test_get_by_id_delegates_to_list_entry_entity(self, resolver) -> None:
        """get_by_id() should delegate to entry.entity when entry.fields not requested."""
        from affinity.models.entities import ListEntryWithEntity

        entry = ListEntryWithEntity.model_validate(
            {
                "id": 1,
                "listId": 100,
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "company",
                "entity": {
                    "id": 1,
                    "name": "Test Co",
                    "fields": [{"id": "field-1", "value": {"data": "Active"}}],
                },
            }
        )
        result = resolver.get_by_id(entry, FieldId(1))
        assert result == "Active"

    def test_get_many_delegates_to_list_entry_entity(self, resolver) -> None:
        """get_many() should work with ListEntryWithEntity via delegation."""
        from affinity.models.entities import ListEntryWithEntity

        entry = ListEntryWithEntity.model_validate(
            {
                "id": 1,
                "listId": 100,
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "company",
                "entity": {
                    "id": 1,
                    "name": "Test Co",
                    "fields": [
                        {"id": "field-1", "value": {"data": "Active"}},
                        {"id": "field-2", "value": {"dropdownOptionId": 100}},
                    ],
                },
            }
        )
        values = resolver.get_many(entry, ["Status", "Stage"])
        assert values == {"Status": "Active", "Stage": 100}

    def test_get_no_delegation_when_entity_is_none(self, resolver) -> None:
        """get() should not delegate when entry.entity is None."""
        from affinity.models.entities import ListEntryWithEntity

        entry = ListEntryWithEntity.model_validate(
            {
                "id": 1,
                "listId": 100,
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "company",
            }
        )
        assert entry.entity is None
        assert not entry.fields.requested

        with pytest.warns(UserWarning, match="Fields were not requested"):
            result = resolver.get(entry, "Status")
        assert result is None

    def test_get_no_delegation_when_entry_fields_requested(self, resolver) -> None:
        """get() should use entry's own fields when entry.fields.requested is True."""
        from affinity.models.entities import ListEntryWithEntity

        entry = ListEntryWithEntity.model_validate(
            {
                "id": 1,
                "listId": 100,
                "createdAt": "2026-01-01T00:00:00Z",
                "type": "company",
                "fields": [{"id": "field-1", "value": {"data": "FromEntry"}}],
                "entity": {
                    "id": 1,
                    "name": "Test Co",
                    "fields": [{"id": "field-1", "value": {"data": "FromEntity"}}],
                },
            }
        )
        assert entry.fields.requested
        assert entry.entity.fields.requested

        result = resolver.get(entry, "Status")
        assert result == "FromEntry"
