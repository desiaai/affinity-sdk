"""Coverage tests for affinity.cli.resolve and affinity.cli.resolvers.

Targets cache paths, async variants, ambiguous resolution, and
dataclass to_dict methods.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from affinity.cli.errors import CLIError
from affinity.cli.resolve import (
    async_resolve_list_selector,
    get_company_fields,
    get_person_fields,
    list_all_saved_views,
    list_fields_for_list,
    resolve_list_selector,
    resolve_saved_view,
)
from affinity.cli.resolvers import (
    ResolvedEntity,
    ResolvedFieldSelection,
    ResolvedList,
    ResolvedSavedView,
    build_resolved_metadata,
)
from affinity.types import ListId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_list(list_id: int = 1, name: str = "Deals") -> MagicMock:
    m = MagicMock()
    m.id = list_id
    m.name = name
    m.type = "deal"
    return m


def _mock_saved_view(view_id: int = 10, name: str = "Active") -> MagicMock:
    m = MagicMock()
    m.id = view_id
    m.name = name
    return m


def _mock_cache(enabled: bool = True) -> MagicMock:
    cache = MagicMock()
    cache.enabled = enabled
    cache.get.return_value = None
    cache.get_list.return_value = None
    return cache


# ---------------------------------------------------------------------------
# resolve_list_selector (sync)
# ---------------------------------------------------------------------------


class TestResolveListSelector:
    def test_by_id(self) -> None:
        client = MagicMock()
        lst = _mock_list(42, "Pipeline")
        client.lists.get.return_value = lst
        result = resolve_list_selector(client=client, selector="42")
        assert result.list is lst
        assert result.resolved["list"]["listId"] == 42

    def test_by_name_single_match(self) -> None:
        client = MagicMock()
        lst = _mock_list(1, "Pipeline")
        client.lists.resolve_all.return_value = [lst]
        result = resolve_list_selector(client=client, selector="Pipeline")
        assert result.list is lst

    def test_by_name_not_found(self) -> None:
        client = MagicMock()
        client.lists.resolve_all.return_value = []
        with pytest.raises(CLIError, match="not found"):
            resolve_list_selector(client=client, selector="NoSuchList")

    def test_by_name_ambiguous(self) -> None:
        client = MagicMock()
        client.lists.resolve_all.return_value = [_mock_list(1, "X"), _mock_list(2, "X")]
        with pytest.raises(CLIError, match="Ambiguous"):
            resolve_list_selector(client=client, selector="X")

    def test_cache_hit(self) -> None:
        client = MagicMock()
        cached_list = _mock_list(99, "Cached")
        cache = _mock_cache()
        cache.get.return_value = cached_list
        result = resolve_list_selector(client=client, selector="Cached", cache=cache)
        assert result.list is cached_list
        assert result.resolved["list"]["cached"] is True
        client.lists.resolve_all.assert_not_called()

    def test_cache_set_on_resolve(self) -> None:
        client = MagicMock()
        lst = _mock_list(5, "New")
        client.lists.resolve_all.return_value = [lst]
        cache = _mock_cache()
        resolve_list_selector(client=client, selector="New", cache=cache)
        cache.set.assert_called_once()


# ---------------------------------------------------------------------------
# async_resolve_list_selector
# ---------------------------------------------------------------------------


class TestAsyncResolveListSelector:
    def test_by_id(self) -> None:
        client = MagicMock(spec=["lists"])
        lst = _mock_list(42, "Pipeline")
        client.lists.get = AsyncMock(return_value=lst)
        result = asyncio.run(async_resolve_list_selector(client=client, selector="42"))
        assert result.list is lst

    def test_by_name_single(self) -> None:
        client = MagicMock(spec=["lists"])
        lst = _mock_list(1, "Sales")
        client.lists.resolve_all = AsyncMock(return_value=[lst])
        result = asyncio.run(async_resolve_list_selector(client=client, selector="Sales"))
        assert result.list is lst

    def test_by_name_not_found(self) -> None:
        client = MagicMock(spec=["lists"])
        client.lists.resolve_all = AsyncMock(return_value=[])
        with pytest.raises(CLIError, match="not found"):
            asyncio.run(async_resolve_list_selector(client=client, selector="Nope"))

    def test_by_name_ambiguous(self) -> None:
        client = MagicMock(spec=["lists"])
        client.lists.resolve_all = AsyncMock(return_value=[_mock_list(1), _mock_list(2)])
        with pytest.raises(CLIError, match="Ambiguous"):
            asyncio.run(async_resolve_list_selector(client=client, selector="Deals"))

    def test_cache_hit(self) -> None:
        client = MagicMock(spec=["lists"])
        cached_list = _mock_list(99, "Cached")
        cache = _mock_cache()
        cache.get.return_value = cached_list
        result = asyncio.run(
            async_resolve_list_selector(client=client, selector="Cached", cache=cache)
        )
        assert result.list is cached_list


# ---------------------------------------------------------------------------
# resolve_saved_view
# ---------------------------------------------------------------------------


class TestResolveSavedView:
    def test_by_id(self) -> None:
        client = MagicMock()
        view = _mock_saved_view(10, "Active")
        client.lists.get_saved_view.return_value = view
        v, _meta = resolve_saved_view(
            client=client,
            list_id=ListId(1),
            selector="10",
        )
        assert v is view

    def test_by_name_single(self) -> None:
        client = MagicMock()
        view = _mock_saved_view(10, "Active")
        client.lists.saved_views_all.return_value = [view]
        v, meta = resolve_saved_view(
            client=client,
            list_id=ListId(1),
            selector="Active",
        )
        assert v is view
        assert meta["savedView"]["name"] == "Active"

    def test_by_name_not_found(self) -> None:
        client = MagicMock()
        client.lists.saved_views_all.return_value = []
        with pytest.raises(CLIError, match="not found"):
            resolve_saved_view(
                client=client,
                list_id=ListId(1),
                selector="NoView",
            )

    def test_by_name_ambiguous(self) -> None:
        client = MagicMock()
        views = [
            _mock_saved_view(1, "V"),
            _mock_saved_view(2, "V"),
        ]
        client.lists.saved_views_all.return_value = views
        with pytest.raises(CLIError, match="Ambiguous"):
            resolve_saved_view(
                client=client,
                list_id=ListId(1),
                selector="V",
            )


# ---------------------------------------------------------------------------
# Cache-enabled field fetchers
# ---------------------------------------------------------------------------


class TestCachedFieldFetchers:
    def test_list_all_saved_views_cache_hit(self) -> None:
        client = MagicMock()
        cache = _mock_cache()
        cached_views = [_mock_saved_view()]
        cache.get_list.return_value = cached_views
        result = list_all_saved_views(client=client, list_id=ListId(1), cache=cache)
        assert result is cached_views
        client.lists.saved_views_all.assert_not_called()

    def test_list_all_saved_views_cache_miss(self) -> None:
        client = MagicMock()
        views = [_mock_saved_view()]
        client.lists.saved_views_all.return_value = views
        cache = _mock_cache()
        result = list_all_saved_views(client=client, list_id=ListId(1), cache=cache)
        assert result == views
        cache.set.assert_called_once()

    def test_list_fields_cache_hit(self) -> None:
        client = MagicMock()
        cache = _mock_cache()
        cached_fields = [MagicMock()]
        cache.get_list.return_value = cached_fields
        result = list_fields_for_list(client=client, list_id=ListId(1), cache=cache)
        assert result is cached_fields

    def test_list_fields_cache_miss(self) -> None:
        client = MagicMock()
        fields = [MagicMock()]
        client.fields.list.return_value = fields
        cache = _mock_cache()
        result = list_fields_for_list(client=client, list_id=ListId(1), cache=cache)
        assert result == fields
        cache.set.assert_called_once()

    def test_person_fields_cache_hit(self) -> None:
        client = MagicMock()
        cache = _mock_cache()
        cached_fields = [MagicMock()]
        cache.get_list.return_value = cached_fields
        result = get_person_fields(client=client, cache=cache)
        assert result is cached_fields

    def test_person_fields_cache_miss(self) -> None:
        client = MagicMock()
        fields = [MagicMock()]
        client.persons.get_fields.return_value = fields
        cache = _mock_cache()
        result = get_person_fields(client=client, cache=cache)
        assert result == fields
        cache.set.assert_called_once()

    def test_company_fields_cache_hit(self) -> None:
        client = MagicMock()
        cache = _mock_cache()
        cached_fields = [MagicMock()]
        cache.get_list.return_value = cached_fields
        result = get_company_fields(client=client, cache=cache)
        assert result is cached_fields

    def test_company_fields_cache_miss(self) -> None:
        client = MagicMock()
        fields = [MagicMock()]
        client.companies.get_fields.return_value = fields
        cache = _mock_cache()
        result = get_company_fields(client=client, cache=cache)
        assert result == fields
        cache.set.assert_called_once()


# ---------------------------------------------------------------------------
# resolvers.py — dataclass to_dict methods
# ---------------------------------------------------------------------------


class TestResolvedEntity:
    def test_to_dict_with_url(self) -> None:
        r = ResolvedEntity(
            input="john@example.com",
            entity_id=123,
            entity_type="person",
            source="email",
            canonical_url="https://app.affinity.co/persons/123",
        )
        d = r.to_dict()
        assert d["personId"] == 123
        assert d["canonicalUrl"] == "https://app.affinity.co/persons/123"
        assert "entity_id" not in d
        assert "entity_type" not in d

    def test_to_dict_without_url(self) -> None:
        r = ResolvedEntity(
            input="42",
            entity_id=42,
            entity_type="company",
            source="id",
        )
        d = r.to_dict()
        assert d["companyId"] == 42
        assert "canonicalUrl" not in d
        assert "canonical_url" not in d


class TestResolvedFieldSelection:
    def test_both_none(self) -> None:
        r = ResolvedFieldSelection()
        assert r.to_dict() == {}

    def test_with_ids(self) -> None:
        r = ResolvedFieldSelection(field_ids=["field-1"])
        assert r.to_dict() == {"fieldIds": ["field-1"]}

    def test_with_types(self) -> None:
        r = ResolvedFieldSelection(field_types=["global"])
        assert r.to_dict() == {"fieldTypes": ["global"]}

    def test_both_set(self) -> None:
        r = ResolvedFieldSelection(field_ids=["field-1"], field_types=["global"])
        d = r.to_dict()
        assert d["fieldIds"] == ["field-1"]
        assert d["fieldTypes"] == ["global"]


class TestResolvedListDataclass:
    def test_to_dict(self) -> None:
        r = ResolvedList(input="Pipeline", list_id=5, source="name")
        assert r.to_dict() == {
            "input": "Pipeline",
            "listId": 5,
            "source": "name",
        }


class TestResolvedSavedView:
    def test_to_dict(self) -> None:
        r = ResolvedSavedView(input="Active Deals", saved_view_id=10, name="Active Deals")
        assert r.to_dict() == {
            "input": "Active Deals",
            "savedViewId": 10,
            "name": "Active Deals",
        }


class TestBuildResolvedMetadata:
    def test_all_params(self) -> None:
        entity = ResolvedEntity(
            input="42",
            entity_id=42,
            entity_type="person",
            source="id",
        )
        list_res = ResolvedList(input="Sales", list_id=1, source="name")
        sv = ResolvedSavedView(input="Active", saved_view_id=10, name="Active")
        fs = ResolvedFieldSelection(field_ids=["field-1"])
        result = build_resolved_metadata(
            entity=entity,
            list_resolution=list_res,
            saved_view=sv,
            field_selection=fs,
            expand=["lists"],
        )
        assert "person" in result
        assert "list" in result
        assert "savedView" in result
        assert "fieldSelection" in result
        assert result["expand"] == ["lists"]

    def test_empty_expand_excluded(self) -> None:
        result = build_resolved_metadata(expand=[])
        assert "expand" not in result

    def test_empty_field_selection_excluded(self) -> None:
        fs = ResolvedFieldSelection()
        result = build_resolved_metadata(field_selection=fs)
        assert "fieldSelection" not in result

    def test_none_params(self) -> None:
        result = build_resolved_metadata()
        assert result == {}
