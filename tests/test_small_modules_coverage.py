from __future__ import annotations

import importlib
import logging

import pytest
from pydantic import TypeAdapter

import affinity
from affinity.exceptions import (
    CompanyNotFoundError,
    EntityNotFoundError,
    OpportunityNotFoundError,
    PersonNotFoundError,
    ValidationError,
    VersionCompatibilityError,
    error_from_response,
)
from affinity.filters import F, Filter, RawFilter
from affinity.models.entities import (
    Company,
    FieldValueCreate,
    FieldValues,
    ListEntryWithEntity,
    Opportunity,
    Person,
    _normalize_null_lists,
)
from affinity.models.pagination import (
    BatchOperationResponse,
    PaginatedResponse,
)
from affinity.models.types import FieldId, ListType, OpenIntEnum, field_id_to_v1_numeric
from affinity.progress import ProgressCallback


def test_progress_callback_protocol_callable_body_executes() -> None:
    ProgressCallback.__call__(None, 0, None, phase="upload")  # type: ignore[misc]


def test_affinity_init_null_handler_branch_via_reload() -> None:
    logger = logging.getLogger("affinity_sdk")
    original_handlers = list(logger.handlers)
    try:
        logger.handlers = []
        reloaded = importlib.reload(affinity)
        assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)

        logger.handlers = [logging.NullHandler()]
        _ = importlib.reload(reloaded)
        assert sum(isinstance(h, logging.NullHandler) for h in logger.handlers) == 1
    finally:
        logger.handlers = original_handlers


def test_exceptions_str_and_entity_not_found_initializers() -> None:
    e = ValidationError("bad", param="x", status_code=400)
    assert "(param: x)" in str(e)
    assert str(ValidationError("bad", param=None, status_code=400)).startswith("[400]")
    assert EntityNotFoundError("Thing", 1).entity_type == "Thing"
    assert isinstance(PersonNotFoundError(1), EntityNotFoundError)
    assert isinstance(CompanyNotFoundError(1), EntityNotFoundError)
    assert isinstance(OpportunityNotFoundError(1), EntityNotFoundError)

    assert "expected_v2_version=" in str(
        VersionCompatibilityError("x", expected_version="2025-01-01", parsing_error=None)
    )
    assert "parsing_error=" in str(
        VersionCompatibilityError("x", expected_version=None, parsing_error="boom")
    )
    assert str(VersionCompatibilityError("x", expected_version=None, parsing_error=None)) == "x"

    err = error_from_response(422, {"errors": [{"message": "m", "param": "p"}]})
    assert isinstance(err, ValidationError)
    assert "param: p" in str(err)
    other = error_from_response(418, {"errors": [{"message": "m"}]})
    assert str(other) == "[418] m"
    assert str(error_from_response(422, {"message": "top"})) == "[422] top"
    assert str(error_from_response(422, {"detail": "detail"})) == "[422] detail"
    assert str(error_from_response(422, {"error": {"message": "nested"}})) == "[422] nested"
    assert str(error_from_response(418, "nope")) == "[418] Unknown error"
    assert str(error_from_response(418, {"errors": ["x"]})) == "[418] x"
    assert str(error_from_response(418, {"errors": [{"message": "m"}, "x"]})) == "[418] m"


def test_filters_str_and_factories_and_field_builder_gte() -> None:
    expr = F.field("age").greater_than_or_equal(10)
    assert str(expr) == "age >= 10"

    combined = Filter.and_(F.field("name").contains("x"), RawFilter("true"))
    assert "&" in str(combined)

    combined_or = Filter.or_(F.field("name").contains("x"), RawFilter("false"))
    assert "|" in str(combined_or)

    with pytest.raises(ValueError):
        Filter.and_()
    with pytest.raises(ValueError):
        Filter.or_()


def test_entities_field_values_coercion_and_null_list_normalization() -> None:
    assert FieldValues.model_validate(None).requested is True
    assert FieldValues.model_validate([]).requested is True
    fv = FieldValues.model_validate({"x": 1})
    assert FieldValues._coerce_from_api(fv) is fv
    assert _normalize_null_lists("x", ("emails",)) == "x"

    person = Person.model_validate(
        {
            "id": 1,
            "type": "external",
            "emails": None,
            "organizationIds": None,
            "opportunityIds": None,
        }
    )
    assert person.emails == []
    assert person.company_ids == []
    assert person.opportunity_ids == []

    entry = ListEntryWithEntity.model_validate(
        {"id": 1, "listId": 10, "createdAt": "2025-01-01T00:00:00Z", "type": "person"}
    )
    assert entry.fields.requested is False
    opportunity = Opportunity.model_validate({"id": 1, "name": "O", "listId": 10})
    assert opportunity.fields.requested is False
    opportunity_2 = Opportunity.model_validate({"id": 2, "name": "O2", "listId": 10, "fields": {}})
    assert opportunity_2.fields.requested is True


def test_field_values_no_double_wrapping() -> None:
    """FieldValues constructed with explicit kwargs should not double-nest data."""
    # Direct construction with empty data
    fv1 = FieldValues(requested=False, data={})
    assert fv1.requested is False
    assert fv1.data == {}

    # Direct construction with field data
    field_data = {"field-1": {"id": "field-1", "name": "Status", "value": {"data": "Active"}}}
    fv2 = FieldValues(requested=True, data=field_data)
    assert fv2.requested is True
    assert fv2.data == field_data

    # Round-trip: model_dump -> model_validate should not double-nest
    company = Company.model_validate({"id": 1, "name": "Test"})
    dumped_fields = company.model_dump(mode="json")["fields"]
    round_tripped = FieldValues.model_validate(dumped_fields)
    assert round_tripped.data == {}
    assert round_tripped.requested is False

    # Raw API dict (no "requested"/"data" keys) should still be wrapped
    raw = {"field-1": {"id": "field-1", "name": "Status"}}
    fv3 = FieldValues.model_validate(raw)
    assert fv3.requested is True
    assert fv3.data == raw


def test_pagination_helpers_len_has_next_and_failures() -> None:
    resp = PaginatedResponse[int](data=[1, 2])
    assert len(resp) == 2

    # Test V1-style pagination with next_page_token (unified into PaginatedResponse)
    v1_style = PaginatedResponse[int](data=[1], next_page_token="t")
    assert v1_style.has_next is True
    assert v1_style.next_cursor == "t"
    v1_empty = PaginatedResponse[int](data=[1], next_page_token=None)
    assert v1_empty.has_next is False
    assert v1_empty.next_cursor is None

    batch = BatchOperationResponse.model_validate(
        {
            "results": [
                {"fieldId": "field-1", "success": True},
                {"fieldId": "field-2", "success": False},
            ]
        }
    )
    assert len(batch.failures) == 1


def test_unified_paginated_response_handles_v1_and_v2_formats() -> None:
    """Test that PaginatedResponse handles both V1 and V2 pagination formats."""
    # V2 format: uses pagination.nextUrl
    v2_json = {
        "data": [1, 2, 3],
        "pagination": {"nextUrl": "https://api.affinity.co/v2/persons?cursor=abc123"},
    }
    v2_response = PaginatedResponse[int].model_validate(v2_json)
    assert v2_response.data == [1, 2, 3]
    assert v2_response.has_next is True
    assert v2_response.next_cursor == "https://api.affinity.co/v2/persons?cursor=abc123"
    assert v2_response.next_page_token is None

    # V1 format: uses nextPageToken
    v1_json = {"data": [4, 5, 6], "nextPageToken": "token123"}
    v1_response = PaginatedResponse[int].model_validate(v1_json)
    assert v1_response.data == [4, 5, 6]
    assert v1_response.has_next is True
    assert v1_response.next_cursor == "token123"
    assert v1_response.next_page_token == "token123"

    # Empty pagination (V2)
    v2_empty = PaginatedResponse[int].model_validate({"data": [1], "pagination": {}})
    assert v2_empty.has_next is False
    assert v2_empty.next_cursor is None

    # Empty pagination (V1)
    v1_empty = PaginatedResponse[int].model_validate({"data": [1]})
    assert v1_empty.has_next is False
    assert v1_empty.next_cursor is None

    # Manual construction with next_page_token (V1 style)
    manual_v1 = PaginatedResponse[int](data=[7, 8], next_page_token="manual_token")
    assert manual_v1.has_next is True
    assert manual_v1.next_cursor == "manual_token"

    # V2 cursor takes precedence over V1 token (both present - unusual but supported)
    # This shouldn't happen in practice, but if both are present, V2 wins
    from affinity.models.pagination import PaginationInfo

    both = PaginatedResponse[int](
        data=[1],
        pagination=PaginationInfo(next_cursor="v2_url"),
        next_page_token="v1_token",
    )
    assert both.next_cursor == "v2_url"  # V2 takes precedence


def test_types_open_int_enum_missing_and_field_id_to_v1_numeric_errors() -> None:
    unknown = ListType(999)
    assert int(unknown) == 999
    assert str(unknown.name).startswith("UNKNOWN_")

    class Local(OpenIntEnum):
        A = 1

    assert int(Local("2")) == 2
    with pytest.raises(ValueError):
        _ = Local("nope")

    assert field_id_to_v1_numeric("field-123") == 123
    with pytest.raises(ValueError):
        field_id_to_v1_numeric("field-x")

    # FieldId pydantic validation paths
    assert FieldValueCreate(field_id="field-123", entity_id=1, value="x").field_id == FieldId(
        "field-123"
    )
    with pytest.raises(ValueError):
        FieldValueCreate(field_id="field-x", entity_id=1, value="x")

    with pytest.raises(ValueError):
        TypeAdapter(FieldId).validate_python(object())
