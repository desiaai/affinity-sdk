"""
Tests for AsyncReminderService.list_batch().
"""

from __future__ import annotations

import httpx
import pytest

from affinity import AsyncAffinity
from affinity.exceptions import AffinityError
from affinity.types import CompanyId, PersonId, ReminderStatus


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_fetches_for_all_companies() -> None:
    """list_batch() should fetch reminders for all given company IDs."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # Note: ReminderService.list() maps company_id -> "organization_id" in the V1 API
        # query string (see v1_only.py ~line 309). We match on the wire format here.
        if "organization_id=1" in url:
            return httpx.Response(
                200,
                json={
                    "reminders": [
                        {
                            "id": 10,
                            "type": 0,
                            "status": 0,
                            "reset_type": 0,
                            "dueDate": "2026-03-01T00:00:00Z",
                            "createdAt": "2026-01-01T00:00:00Z",
                        }
                    ]
                },
            )
        if "organization_id=2" in url:
            return httpx.Response(
                200,
                json={
                    "reminders": [
                        {
                            "id": 20,
                            "type": 0,
                            "status": 0,
                            "reset_type": 0,
                            "dueDate": "2026-03-01T00:00:00Z",
                            "createdAt": "2026-01-01T00:00:00Z",
                        },
                        {
                            "id": 21,
                            "type": 0,
                            "status": 0,
                            "reset_type": 0,
                            "dueDate": "2026-03-01T00:00:00Z",
                            "createdAt": "2026-01-01T00:00:00Z",
                        },
                    ]
                },
            )
        return httpx.Response(200, json={"reminders": []})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.reminders.list_batch(
            company_ids=[CompanyId(1), CompanyId(2), CompanyId(3)],
            max_concurrent=2,
        )

    assert len(results) == 3
    assert len(results[1]) == 1
    assert len(results[2]) == 2
    assert len(results[3]) == 0  # empty list, not omitted


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_empty_input() -> None:
    """list_batch() with empty IDs should return empty dict."""

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Unexpected API call")

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.reminders.list_batch(company_ids=[])
    assert results == {}


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_requires_exactly_one_entity_type() -> None:
    """list_batch() should reject ambiguous or missing entity type."""
    async_transport = httpx.MockTransport(lambda _r: httpx.Response(200, json={}))
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        # No entity type
        with pytest.raises(ValueError, match="Exactly one"):
            await client.reminders.list_batch()

        # Multiple entity types
        with pytest.raises(ValueError, match="Exactly one"):
            await client.reminders.list_batch(person_ids=[PersonId(1)], company_ids=[CompanyId(2)])


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_passes_filters() -> None:
    """list_batch() should pass common filters to each iter() call."""
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"reminders": []})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        await client.reminders.list_batch(
            person_ids=[PersonId(1)],
            status=ReminderStatus.ACTIVE,
        )

    assert len(captured_urls) == 1
    assert "person_id=1" in captured_urls[0]
    assert "status=1" in captured_urls[0]  # ReminderStatus.ACTIVE == 1


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_on_error_skip() -> None:
    """list_batch(on_error='skip') should skip failed entities."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "person_id=2" in url:
            return httpx.Response(500, json={"error": "Server error"})
        return httpx.Response(200, json={"reminders": []})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.reminders.list_batch(
            person_ids=[PersonId(1), PersonId(2), PersonId(3)],
            on_error="skip",
        )

    # All entities are in results; person 2 failed on first page so has empty list
    assert 1 in results
    assert 2 in results
    assert results[2] == []  # error on first page -> no reminders collected
    assert 3 in results


@pytest.mark.req("SDK-REMINDER-LIST-BATCH")
@pytest.mark.asyncio
async def test_list_batch_on_error_raise() -> None:
    """list_batch(on_error='raise') should raise and cancel remaining tasks."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "person_id=2" in url:
            return httpx.Response(500, json={"error": "Server error"})
        return httpx.Response(200, json={"reminders": []})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        with pytest.raises(AffinityError):
            await client.reminders.list_batch(
                person_ids=[PersonId(1), PersonId(2)],
                on_error="raise",
            )
