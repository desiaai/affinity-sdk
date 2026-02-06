"""
Tests for AsyncEntityFileService.batch_get().
"""

from __future__ import annotations

import httpx
import pytest

from affinity import AsyncAffinity
from affinity.exceptions import NotFoundError
from affinity.types import FileId


@pytest.mark.req("SDK-FILE-BATCH-GET")
@pytest.mark.asyncio
async def test_file_batch_get_fetches_all() -> None:
    """batch_get() should fetch all file metadata concurrently."""

    def handler(request: httpx.Request) -> httpx.Response:
        file_id = int(request.url.path.split("/")[-1])
        return httpx.Response(
            200,
            json={
                "id": file_id,
                "name": f"file-{file_id}.pdf",
                "size": file_id * 100,
                "uploaderId": 10,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.files.batch_get([FileId(1), FileId(2), FileId(3)], max_concurrent=2)

    assert len(results) == 3
    assert results[FileId(1)].name == "file-1.pdf"


@pytest.mark.req("SDK-FILE-BATCH-GET")
@pytest.mark.asyncio
async def test_file_batch_get_empty_input() -> None:
    """batch_get([]) should return empty dict without API calls."""

    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Unexpected API call")

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.files.batch_get([])
    assert results == {}


@pytest.mark.req("SDK-FILE-BATCH-GET")
@pytest.mark.asyncio
async def test_file_batch_get_deduplicates_ids() -> None:
    """batch_get() should deduplicate file IDs."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        file_id = int(request.url.path.split("/")[-1])
        return httpx.Response(
            200,
            json={
                "id": file_id,
                "name": "f.txt",
                "size": 10,
                "uploaderId": 10,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.files.batch_get([FileId(1), FileId(1), FileId(2), FileId(2)])

    assert len(results) == 2
    assert call_count == 2


@pytest.mark.req("SDK-FILE-BATCH-GET")
@pytest.mark.asyncio
async def test_file_batch_get_on_error_skip() -> None:
    """batch_get(on_error='skip') should return partial results."""

    def handler(request: httpx.Request) -> httpx.Response:
        file_id = int(request.url.path.split("/")[-1])
        if file_id == 2:
            return httpx.Response(404, json={"error": "Not found"})
        return httpx.Response(
            200,
            json={
                "id": file_id,
                "name": "f.txt",
                "size": 10,
                "uploaderId": 10,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        results = await client.files.batch_get([FileId(1), FileId(2), FileId(3)], on_error="skip")

    assert len(results) == 2
    assert FileId(2) not in results


@pytest.mark.req("SDK-FILE-BATCH-GET")
@pytest.mark.asyncio
async def test_file_batch_get_on_error_raise() -> None:
    """batch_get(on_error='raise') should raise on first error."""

    def handler(request: httpx.Request) -> httpx.Response:
        file_id = int(request.url.path.split("/")[-1])
        if file_id == 2:
            return httpx.Response(404, json={"error": "Not found"})
        return httpx.Response(
            200,
            json={
                "id": file_id,
                "name": "f.txt",
                "size": 10,
                "uploaderId": 10,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )

    async_transport = httpx.MockTransport(handler)
    async with AsyncAffinity(
        api_key="test", max_retries=0, async_transport=async_transport
    ) as client:
        with pytest.raises(NotFoundError):
            await client.files.batch_get([FileId(1), FileId(2)], on_error="raise")
