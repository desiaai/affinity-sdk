"""
Tests for FieldService.list() caching and falsy ID fix.
"""

from __future__ import annotations

import httpx
import pytest

from affinity import Affinity
from affinity.types import EntityType, ListId


@pytest.mark.req("SDK-FIELD-CACHING")
def test_field_service_list_uses_cache() -> None:
    """FieldService.list() should cache results."""
    call_count: int = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": [{"id": 1, "name": "Status", "valueType": 1}]})

    transport = httpx.MockTransport(handler)
    with Affinity(
        api_key="test",
        enable_cache=True,
        max_retries=0,
        transport=transport,
    ) as client:
        fields1 = client.fields.list()
        assert len(fields1) == 1

        fields2 = client.fields.list()
        assert len(fields2) == 1

        # Only one API call should have been made
        assert call_count == 1


@pytest.mark.req("SDK-FIELD-CACHING")
def test_field_service_list_cache_key_varies_by_params() -> None:
    """Different parameters should use different cache keys."""
    call_count: int = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    with Affinity(
        api_key="test",
        enable_cache=True,
        max_retries=0,
        transport=transport,
    ) as client:
        client.fields.list()
        client.fields.list(list_id=ListId(123))
        client.fields.list(entity_type=EntityType.PERSON)

        # Three different cache keys = three API calls
        assert call_count == 3


@pytest.mark.req("SDK-FIELD-CACHING")
def test_field_service_list_falsy_id_not_skipped() -> None:
    """list_id=ListId(0) should be sent as a parameter, not skipped."""
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    with Affinity(api_key="test", max_retries=0, transport=transport) as client:
        client.fields.list(list_id=ListId(0))

    assert captured_request is not None
    assert "list_id=0" in str(captured_request.url)
