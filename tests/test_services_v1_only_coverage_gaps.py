"""Additional tests for affinity.services.v1_only to improve coverage."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from affinity.clients.http import ClientConfig, HTTPClient
from affinity.exceptions import AffinityError
from affinity.models.types import (
    CompanyId,
    FieldId,
    InteractionType,
    ListEntryId,
    OpportunityId,
    PersonId,
)
from affinity.services.v1_only import (
    FieldValueChangesService,
    FieldValueService,
    InteractionService,
)


class TestInteractionServiceCoverage:
    """Tests for uncovered branches in InteractionService."""

    def test_list_requires_type_parameter(self) -> None:
        """Test that list() raises ValueError when type is not provided."""
        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
            )
        )
        service = InteractionService(http)

        with pytest.raises(ValueError, match="type is required"):
            service.list(company_id=CompanyId(100))

    def test_list_with_company_id_filter(self) -> None:
        """Test filtering interactions by company_id (organization_id in V1)."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "organization_id=100" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "interactions": [
                        {
                            "id": 1,
                            "type": 0,
                            "date": "2024-01-01T00:00:00Z",
                            "subject": "Test",
                            "bodies": [],
                            "attendees": [],
                        }
                    ],
                    "next_page_token": None,
                },
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = InteractionService(http)

        result = service.list(
            type=InteractionType.EMAIL,
            company_id=CompanyId(100),
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert len(result.data) == 1

    def test_list_with_opportunity_id_filter(self) -> None:
        """Test filtering interactions by opportunity_id."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "opportunity_id=200" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "interactions": [
                        {
                            "id": 1,
                            "type": 0,
                            "date": "2024-01-01T00:00:00Z",
                            "subject": "Test",
                            "bodies": [],
                            "attendees": [],
                        }
                    ],
                    "next_page_token": None,
                },
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = InteractionService(http)

        result = service.list(
            type=InteractionType.EMAIL,
            opportunity_id=OpportunityId(200),
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert len(result.data) == 1


class TestFieldValueServiceListBatch:
    """Tests for list_batch method in FieldValueService."""

    def test_list_batch_with_company_ids(self) -> None:
        """Test list_batch with company_ids."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "id": call_count * 100,
                        "fieldId": 1,
                        "entityId": call_count,
                        "value": "test",
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueService(http)

        result = service.list_batch(company_ids=[CompanyId(1), CompanyId(2)])
        assert len(result) == 2
        assert CompanyId(1) in result
        assert CompanyId(2) in result

    def test_list_batch_with_opportunity_ids(self) -> None:
        """Test list_batch with opportunity_ids."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "id": call_count * 100,
                        "fieldId": 1,
                        "entityId": call_count,
                        "value": "test",
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueService(http)

        result = service.list_batch(opportunity_ids=[OpportunityId(1), OpportunityId(2)])
        assert len(result) == 2
        assert OpportunityId(1) in result
        assert OpportunityId(2) in result

    def test_list_batch_skips_on_error(self) -> None:
        """Test list_batch with on_error='skip' skips failed entities."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(404, json={"error": "Not found"}, request=request)
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 200,
                        "fieldId": 1,
                        "entityId": 2,
                        "value": "test",
                        "created_at": "2024-01-01T00:00:00Z",
                    }
                ],
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueService(http)

        # Should skip the failed entity and return just the successful one
        result = service.list_batch(person_ids=[PersonId(1), PersonId(2)], on_error="skip")
        assert len(result) == 1
        assert PersonId(2) in result

    def test_list_batch_raises_on_affinity_error(self) -> None:
        """Test list_batch with on_error='raise' raises on AffinityError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "Not found"}, request=request)

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueService(http)

        with pytest.raises(AffinityError):
            service.list_batch(person_ids=[PersonId(1)], on_error="raise")


class TestFieldValueChangesServiceCoverage:
    """Tests for uncovered branches in FieldValueChangesService."""

    def test_list_with_opportunity_id(self) -> None:
        """Test listing field value changes with opportunity_id filter."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "opportunity_id=300" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "fieldId": 10,
                            "entityId": 300,
                            "actionType": 0,
                            "value": "new value",
                            "changedAt": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueChangesService(http)

        result = service.list(FieldId(10), opportunity_id=OpportunityId(300))
        assert len(result) == 1

    def test_list_with_list_entry_id(self) -> None:
        """Test listing field value changes with list_entry_id filter."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "list_entry_id=400" in str(request.url)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "fieldId": 10,
                            "entityId": 100,
                            "actionType": 1,
                            "value": "updated",
                            "changedAt": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueChangesService(http)

        result = service.list(FieldId(10), list_entry_id=ListEntryId(400))
        assert len(result) == 1

    def test_list_with_invalid_data_returns_empty(self) -> None:
        """Test list returns empty when data is not a list."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": "not a list"},
                request=request,
            )

        http = HTTPClient(
            ClientConfig(
                api_key="test",
                v1_base_url="https://v1.example",
                v2_base_url="https://v2.example/v2",
                max_retries=0,
                transport=httpx.MockTransport(handler),
            )
        )
        service = FieldValueChangesService(http)

        result = service.list(FieldId(10), person_id=PersonId(1))
        assert result == []
