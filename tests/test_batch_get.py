"""
Tests for batch_get() on async services.
"""

from __future__ import annotations

import httpx
import pytest

from affinity import AsyncAffinity
from affinity.exceptions import NotFoundError
from affinity.types import CompanyId


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_fetches_all_companies() -> None:
    """batch_get() should fetch all companies with concurrency."""

    def handler(request: httpx.Request) -> httpx.Response:
        company_id: int = int(request.url.path.split("/")[-1])
        return httpx.Response(200, json={"id": company_id, "name": f"Company {company_id}"})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.companies.batch_get(
            [CompanyId(1), CompanyId(2), CompanyId(3)],
            max_concurrent=2,
        )

    assert len(results) == 3
    assert results[CompanyId(1)].name == "Company 1"


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_respects_max_concurrent() -> None:
    """batch_get() should process in chunks of max_concurrent."""
    received_ids: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        company_id: int = int(request.url.path.split("/")[-1])
        received_ids.append(company_id)
        return httpx.Response(200, json={"id": company_id, "name": f"Company {company_id}"})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test",
        max_retries=0,
        async_transport=async_transport,
    ) as client:
        results = await client.companies.batch_get(
            [CompanyId(i) for i in range(1, 6)],
            max_concurrent=2,
        )

    assert len(results) == 5
    assert set(received_ids) == {1, 2, 3, 4, 5}

    # Verify chunk ordering: chunk N completes before chunk N+1 starts
    chunk_0 = set(received_ids[:2])
    chunk_1 = set(received_ids[2:4])
    chunk_2 = set(received_ids[4:])
    assert chunk_0 == {1, 2}
    assert chunk_1 == {3, 4}
    assert chunk_2 == {5}


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_empty_input() -> None:
    """batch_get([]) should return empty dict without making API calls."""

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail(f"Unexpected API call: {request.url}")

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.companies.batch_get([])
    assert results == {}


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_deduplicates_ids() -> None:
    """batch_get() should deduplicate IDs and make only one call per unique ID."""
    call_count: int = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        company_id: int = int(request.url.path.split("/")[-1])
        return httpx.Response(200, json={"id": company_id, "name": f"Company {company_id}"})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.companies.batch_get(
            [CompanyId(1), CompanyId(1), CompanyId(2), CompanyId(2)],
        )

    assert len(results) == 2
    assert call_count == 2


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_on_error_skip() -> None:
    """batch_get(on_error='skip') should return partial results."""

    def handler(request: httpx.Request) -> httpx.Response:
        company_id: int = int(request.url.path.split("/")[-1])
        if company_id == 2:
            return httpx.Response(404, json={"error": "Not found"})
        return httpx.Response(200, json={"id": company_id, "name": f"Company {company_id}"})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.companies.batch_get(
            [CompanyId(1), CompanyId(2), CompanyId(3)],
            on_error="skip",
        )

    assert len(results) == 2
    assert CompanyId(1) in results
    assert CompanyId(2) not in results
    assert CompanyId(3) in results


@pytest.mark.req("SDK-BATCH-GET")
@pytest.mark.asyncio
async def test_batch_get_on_error_raise() -> None:
    """batch_get(on_error='raise') should raise on first error."""

    def handler(request: httpx.Request) -> httpx.Response:
        company_id: int = int(request.url.path.split("/")[-1])
        if company_id == 2:
            return httpx.Response(404, json={"error": "Not found"})
        return httpx.Response(200, json={"id": company_id, "name": f"Company {company_id}"})

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        with pytest.raises(NotFoundError):
            await client.companies.batch_get(
                [CompanyId(1), CompanyId(2)],
                on_error="raise",
            )
