from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx

from affinity.clients.http import ClientConfig, HTTPClient
from affinity.models.secondary import InteractionCreate, InteractionUpdate
from affinity.services.v1_only import EntityFileService, InteractionService
from affinity.types import InteractionType, PersonId


def test_v1_interactions_list_parses_type_specific_keys() -> None:
    created_at = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/interactions"):
            payload = {
                "emails": [{"id": 1, "type": int(InteractionType.EMAIL), "date": created_at}],
                "next_page_token": None,
            }
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(404, json={}, request=request)

    http = HTTPClient(
        ClientConfig(
            api_key="k",
            v1_base_url="https://v1.example",
            v2_base_url="https://v2.example/v2",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        service = InteractionService(http)
        page = service.list(
            type=InteractionType.EMAIL,
            person_id=PersonId(1),
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        assert len(page.data) == 1
        assert page.data[0].id == 1
        assert page.data[0].type == int(InteractionType.EMAIL)
    finally:
        http.close()


def test_v1_create_interaction_uses_documented_payload_shape() -> None:
    seen: dict[str, object] = {}
    created_at = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/interactions"):
            seen["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "id": 10,
                    "type": int(InteractionType.MEETING),
                    "date": created_at.isoformat(),
                },
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    http = HTTPClient(
        ClientConfig(
            api_key="k",
            v1_base_url="https://v1.example",
            v2_base_url="https://v2.example/v2",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        service = InteractionService(http)
        created = service.create(
            InteractionCreate(
                type=InteractionType.MEETING,
                person_ids=[PersonId(1), PersonId(2)],
                content="hello",
                date=created_at,
            )
        )
        assert created.id == 10

        payload = seen["json"]
        assert isinstance(payload, dict)
        assert payload["type"] == int(InteractionType.MEETING)
        assert payload["person_ids"] == [1, 2]
        assert payload["content"] == "hello"
        assert payload["date"] == created_at.isoformat()
    finally:
        http.close()


def test_v1_update_interaction_uses_documented_payload_shape() -> None:
    seen: dict[str, object] = {}
    updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith("/interactions/123"):
            seen["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "type": int(InteractionType.MEETING),
                    "date": updated_at.isoformat(),
                },
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    http = HTTPClient(
        ClientConfig(
            api_key="k",
            v1_base_url="https://v1.example",
            v2_base_url="https://v2.example/v2",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        service = InteractionService(http)
        updated = service.update(
            123,
            InteractionType.MEETING,
            InteractionUpdate(content="updated", date=updated_at),
        )
        assert updated.id == 123

        payload = seen["json"]
        assert isinstance(payload, dict)
        assert payload["type"] == int(InteractionType.MEETING)
        assert payload["content"] == "updated"
        assert payload["date"] == updated_at.isoformat()
    finally:
        http.close()


def test_v1_entity_file_download_uses_correct_path_and_follows_redirects() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.method == "GET" and request.url.path.endswith("/entity-files/download/5"):
            return httpx.Response(
                302,
                headers={"Location": "https://files.example/content.bin"},
                request=request,
            )
        if request.method == "GET" and request.url.host == "files.example":
            return httpx.Response(200, content=b"ok", request=request)
        return httpx.Response(404, json={}, request=request)

    http = HTTPClient(
        ClientConfig(
            api_key="k",
            v1_base_url="https://v1.example",
            v2_base_url="https://v2.example/v2",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        service = EntityFileService(http)
        content = service.download(5)
        assert content == b"ok"
        assert calls[0] == "https://v1.example/entity-files/download/5"
        assert calls[1] == "https://files.example/content.bin"
    finally:
        http.close()


def test_v1_entity_file_upload_returns_success_bool() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/entity-files"):
            return httpx.Response(200, json={"success": True}, request=request)
        return httpx.Response(404, json={}, request=request)

    http = HTTPClient(
        ClientConfig(
            api_key="k",
            v1_base_url="https://v1.example",
            v2_base_url="https://v2.example/v2",
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        service = EntityFileService(http)
        ok = service.upload(
            files={"file": ("test.txt", b"hello", "text/plain")},
            person_id=PersonId(1),
        )
        assert ok is True
    finally:
        http.close()
