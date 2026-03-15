"""Tests for query listEntries relationship includes.

Tests the list_entry_indirect fetch strategy that enables:
- include: ["persons"] for listEntries
- include: ["companies"] for listEntries
- include: ["opportunities"] for listEntries
- include: ["interactions"] for listEntries

Related: docs/internal/query-list-export-parity-plan.md
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from affinity.cli.query.executor import QueryExecutor
from affinity.cli.query.models import Query


class TestFetchPersonsForListEntries:
    """Tests for _fetch_persons_for_list_entries handler."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-001")
    @pytest.mark.asyncio
    async def test_person_entry_returns_self(self) -> None:
        """Person list entries return the person as their own associated person."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        # Mock client
        mock_client = MagicMock()
        mock_client.persons = MagicMock()

        # Mock batch fetch
        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 1, "firstName": "John", "lastName": "Doe"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_persons_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        assert len(results[100]) == 1
        assert results[100][0]["firstName"] == "John"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-001")
    @pytest.mark.asyncio
    async def test_company_entry_fetches_associated_persons(self) -> None:
        """Company list entries fetch associated persons via get_associated_person_ids."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "company"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        # Mock client
        mock_client = MagicMock()
        mock_client.companies = MagicMock()
        mock_client.companies.get_associated_person_ids = AsyncMock(return_value=[10, 11])

        # Mock batch fetch
        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [
                {"id": 10, "firstName": "Alice"},
                {"id": 11, "firstName": "Bob"},
            ]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_persons_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        assert len(results[100]) == 2
        assert results[100][0]["firstName"] == "Alice"
        assert results[100][1]["firstName"] == "Bob"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-001")
    @pytest.mark.asyncio
    async def test_opportunity_entry_fetches_associated_persons(self) -> None:
        """Opportunity list entries fetch associated persons via get_associated_person_ids."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "opportunity"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        # Mock client
        mock_client = MagicMock()
        mock_client.opportunities = MagicMock()
        mock_client.opportunities.get_associated_person_ids = AsyncMock(return_value=[10])

        # Mock batch fetch
        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 10, "firstName": "Carol"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_persons_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        assert len(results[100]) == 1
        assert results[100][0]["firstName"] == "Carol"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-001")
    @pytest.mark.asyncio
    async def test_v1_integer_entity_type_person(self) -> None:
        """V1 entityType format (0 = person) is handled correctly."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": 0},  # V1 integer format
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 1, "firstName": "John"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_persons_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        assert len(results[100]) == 1

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-001")
    @pytest.mark.asyncio
    async def test_v1_integer_entity_type_company(self) -> None:
        """V1 entityType format (1 = company) is handled correctly."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": 1},  # V1 integer format
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()
        mock_client.companies = MagicMock()
        mock_client.companies.get_associated_person_ids = AsyncMock(return_value=[10])

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 10, "firstName": "Alice"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_persons_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        assert len(results[100]) == 1


class TestFetchCompaniesForListEntries:
    """Tests for _fetch_companies_for_list_entries handler."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-002")
    @pytest.mark.asyncio
    async def test_company_entry_returns_self(self) -> None:
        """Company list entries return the company as their own associated company."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "company"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 1, "name": "Acme Corp"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_companies_for_list_entries(
                entries, results, asyncio.Semaphore(50)
            )

        assert 100 in results
        assert len(results[100]) == 1
        assert results[100][0]["name"] == "Acme Corp"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-002")
    @pytest.mark.asyncio
    async def test_person_entry_fetches_associated_companies(self) -> None:
        """Person list entries fetch associated companies via get_associated_company_ids."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()
        mock_client.persons = MagicMock()
        mock_client.persons.get_associated_company_ids = AsyncMock(return_value=[10, 11])

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [
                {"id": 10, "name": "Acme"},
                {"id": 11, "name": "Beta"},
            ]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_companies_for_list_entries(
                entries, results, asyncio.Semaphore(50)
            )

        assert 100 in results
        assert len(results[100]) == 2

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-002")
    @pytest.mark.asyncio
    async def test_v1_organization_entity_type(self) -> None:
        """V1/V2 'organization' entityType is handled as company."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "organization"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 1, "name": "Acme Corp"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_companies_for_list_entries(
                entries, results, asyncio.Semaphore(50)
            )

        assert 100 in results
        assert len(results[100]) == 1


class TestFetchOpportunitiesForListEntries:
    """Tests for _fetch_opportunities_for_list_entries handler."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-003")
    @pytest.mark.asyncio
    async def test_opportunity_entry_returns_self(self) -> None:
        """Opportunity list entries return the opportunity as their own."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "opportunity"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 1, "name": "Big Deal"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_opportunities_for_list_entries(
                entries, results, asyncio.Semaphore(50)
            )

        assert 100 in results
        assert len(results[100]) == 1
        assert results[100][0]["name"] == "Big Deal"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-003")
    @pytest.mark.asyncio
    async def test_person_entry_fetches_associated_opportunities(self) -> None:
        """Person list entries fetch associated opportunities."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()
        mock_client.persons = MagicMock()
        mock_client.persons.get_associated_opportunity_ids = AsyncMock(return_value=[10])

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            mock_batch.return_value = [{"id": 10, "name": "Deal A"}]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_opportunities_for_list_entries(
                entries, results, asyncio.Semaphore(50)
            )

        assert 100 in results
        assert len(results[100]) == 1

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-003")
    @pytest.mark.asyncio
    async def test_list_id_filters_opportunities(self) -> None:
        """Opportunities can be filtered to a specific list via list_id."""
        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        mock_client = MagicMock()
        mock_client.persons = MagicMock()
        mock_client.persons.get_associated_opportunity_ids = AsyncMock(return_value=[10, 11])

        with patch.object(QueryExecutor, "_batch_fetch_by_ids") as mock_batch:
            # Two opportunities, only one in target list
            mock_batch.return_value = [
                {"id": 10, "name": "Deal A", "listId": 999},
                {"id": 11, "name": "Deal B", "listId": 888},
            ]

            executor = QueryExecutor.__new__(QueryExecutor)
            executor.client = mock_client
            executor.rate_limiter = AsyncMock()
            executor.rate_limiter.__aenter__ = AsyncMock()
            executor.rate_limiter.__aexit__ = AsyncMock()

            import asyncio

            await executor._fetch_opportunities_for_list_entries(
                entries, results, asyncio.Semaphore(50), list_id=999
            )

        assert 100 in results
        # Only the opportunity in list 999 should be returned
        assert len(results[100]) == 1
        assert results[100][0]["name"] == "Deal A"


class TestFetchInteractionsForListEntries:
    """Tests for _fetch_interactions_for_list_entries handler."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-004")
    @pytest.mark.asyncio
    async def test_fetches_interactions_for_person_entry(self) -> None:
        """Person list entries fetch interactions with person_id filter."""
        from unittest.mock import AsyncMock

        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        # Create mock interaction objects
        class MockInteraction:
            def __init__(self, data: dict[str, Any]):
                self._data = data

            def model_dump(self, mode: str = "python", by_alias: bool = False) -> dict[str, Any]:  # noqa: ARG002
                return self._data

        mock_interactions = [
            MockInteraction({"id": 1, "type": "email", "happenedAt": "2026-01-10"}),
            MockInteraction({"id": 2, "type": "meeting", "happenedAt": "2026-01-11"}),
        ]

        async def mock_iter(*_args: Any, **_kwargs: Any) -> Any:
            for i in mock_interactions:
                yield i

        mock_client = MagicMock()
        mock_client.interactions = MagicMock()
        mock_client.interactions.iter = mock_iter

        executor = QueryExecutor.__new__(QueryExecutor)
        executor.client = mock_client
        executor.rate_limiter = AsyncMock()
        executor.rate_limiter.__aenter__ = AsyncMock()
        executor.rate_limiter.__aexit__ = AsyncMock()

        import asyncio

        await executor._fetch_interactions_for_list_entries(
            entries, results, asyncio.Semaphore(50), limit=10, days=30
        )

        assert 100 in results
        # _fetch_interactions_for_entity iterates all 4 InteractionTypes,
        # mock yields 2 items per type → 8 total (capped by limit=10)
        assert len(results[100]) == 8
        assert results[100][0]["type"] == "email"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-004")
    @pytest.mark.asyncio
    async def test_limit_applies_to_interactions(self) -> None:
        """Limit parameter restricts number of interactions returned."""
        from unittest.mock import AsyncMock

        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        class MockInteraction:
            def __init__(self, data: dict[str, Any]):
                self._data = data

            def model_dump(self, mode: str = "python", by_alias: bool = False) -> dict[str, Any]:  # noqa: ARG002
                return self._data

        # Create 10 mock interactions
        mock_interactions = [MockInteraction({"id": i, "type": "email"}) for i in range(10)]

        async def mock_iter(*_args: Any, **_kwargs: Any) -> Any:
            for i in mock_interactions:
                yield i

        mock_client = MagicMock()
        mock_client.interactions = MagicMock()
        mock_client.interactions.iter = mock_iter

        executor = QueryExecutor.__new__(QueryExecutor)
        executor.client = mock_client
        executor.rate_limiter = AsyncMock()
        executor.rate_limiter.__aenter__ = AsyncMock()
        executor.rate_limiter.__aexit__ = AsyncMock()

        import asyncio

        await executor._fetch_interactions_for_list_entries(
            entries, results, asyncio.Semaphore(50), limit=3, days=30
        )

        assert 100 in results
        # Should only have 3 interactions due to limit
        assert len(results[100]) == 3

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-004")
    @pytest.mark.asyncio
    async def test_default_limit_is_100(self) -> None:
        """Default limit for interactions is 100."""
        from unittest.mock import AsyncMock

        entries = [
            {"id": 100, "entityId": 1, "entityType": "person"},
        ]
        results: dict[int, list[dict[str, Any]]] = {}

        class MockInteraction:
            def __init__(self, data: dict[str, Any]):
                self._data = data

            def model_dump(self, mode: str = "python", by_alias: bool = False) -> dict[str, Any]:  # noqa: ARG002
                return self._data

        # Create 150 mock interactions
        mock_interactions = [MockInteraction({"id": i, "type": "email"}) for i in range(150)]

        async def mock_iter(*_args: Any, **_kwargs: Any) -> Any:
            for i in mock_interactions:
                yield i

        mock_client = MagicMock()
        mock_client.interactions = MagicMock()
        mock_client.interactions.iter = mock_iter

        executor = QueryExecutor.__new__(QueryExecutor)
        executor.client = mock_client
        executor.rate_limiter = AsyncMock()
        executor.rate_limiter.__aenter__ = AsyncMock()
        executor.rate_limiter.__aexit__ = AsyncMock()

        import asyncio

        # No limit specified - should default to 100
        await executor._fetch_interactions_for_list_entries(entries, results, asyncio.Semaphore(50))

        assert 100 in results
        # Should have exactly 100 interactions (default limit)
        assert len(results[100]) == 100


class TestListEntryIndirectFetchStrategy:
    """Tests for the list_entry_indirect fetch strategy dispatch."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-005")
    def test_schema_defines_persons_relationship(self) -> None:
        """listEntries schema defines persons relationship with list_entry_indirect strategy."""
        from affinity.cli.query.schema import SCHEMA_REGISTRY

        list_entries_schema = SCHEMA_REGISTRY["listEntries"]
        assert "persons" in list_entries_schema.relationships

        rel = list_entries_schema.relationships["persons"]
        assert rel.fetch_strategy == "list_entry_indirect"
        assert rel.method_or_service == "persons"
        assert rel.cardinality == "many"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-005")
    def test_schema_defines_companies_relationship(self) -> None:
        """listEntries schema defines companies relationship with list_entry_indirect strategy."""
        from affinity.cli.query.schema import SCHEMA_REGISTRY

        list_entries_schema = SCHEMA_REGISTRY["listEntries"]
        assert "companies" in list_entries_schema.relationships

        rel = list_entries_schema.relationships["companies"]
        assert rel.fetch_strategy == "list_entry_indirect"
        assert rel.method_or_service == "companies"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-005")
    def test_schema_defines_opportunities_relationship(self) -> None:
        """listEntries schema defines opportunities relationship."""
        from affinity.cli.query.schema import SCHEMA_REGISTRY

        list_entries_schema = SCHEMA_REGISTRY["listEntries"]
        assert "opportunities" in list_entries_schema.relationships

        rel = list_entries_schema.relationships["opportunities"]
        assert rel.fetch_strategy == "list_entry_indirect"
        assert rel.method_or_service == "opportunities"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-005")
    def test_schema_defines_interactions_relationship(self) -> None:
        """listEntries schema defines interactions relationship."""
        from affinity.cli.query.schema import SCHEMA_REGISTRY

        list_entries_schema = SCHEMA_REGISTRY["listEntries"]
        assert "interactions" in list_entries_schema.relationships

        rel = list_entries_schema.relationships["interactions"]
        assert rel.fetch_strategy == "list_entry_indirect"
        assert rel.method_or_service == "interactions"


class TestIncludeConfigParameters:
    """Tests for IncludeConfig parameters used by list_entry_indirect."""

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-006")
    def test_include_config_supports_limit(self) -> None:
        """IncludeConfig supports limit parameter."""
        from affinity.cli.query.models import IncludeConfig

        config = IncludeConfig(limit=50)
        assert config.limit == 50

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-006")
    def test_include_config_supports_days(self) -> None:
        """IncludeConfig supports days parameter."""
        from affinity.cli.query.models import IncludeConfig

        config = IncludeConfig(days=180)
        assert config.days == 180

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-006")
    def test_include_config_supports_where(self) -> None:
        """IncludeConfig supports where parameter for filtering."""
        from affinity.cli.query.models import IncludeConfig

        config = IncludeConfig(where={"path": "name", "op": "contains", "value": "Smith"})
        assert config.where is not None
        # WhereClause is a TypedDict, access via dict conversion
        where_dict = config.where if isinstance(config.where, dict) else dict(config.where)
        assert where_dict["path"] == "name"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-006")
    def test_include_config_supports_list_alias(self) -> None:
        """IncludeConfig supports list parameter (aliased to list_)."""
        from affinity.cli.query.models import IncludeConfig

        # Using alias
        config = IncludeConfig.model_validate({"list": "Pipeline"})
        assert config.list_ == "Pipeline"

        # Using field name
        config = IncludeConfig(list_="Pipeline")
        assert config.list_ == "Pipeline"

    @pytest.mark.req("QUERY-LIST-ENTRY-INCLUDE-006")
    def test_query_parses_parameterized_include(self) -> None:
        """Query model parses parameterized include syntax."""
        query = Query.model_validate(
            {
                "from": "listEntries",
                "where": {"path": "listName", "op": "eq", "value": "Dealflow"},
                "include": [
                    "persons",
                    {"interactions": {"limit": 50, "days": 180}},
                    {"opportunities": {"list": "Pipeline"}},
                ],
            }
        )

        assert query.include is not None
        assert "persons" in query.include
        assert "interactions" in query.include
        assert "opportunities" in query.include

        interactions_config = query.include["interactions"]
        assert interactions_config.limit == 50
        assert interactions_config.days == 180

        opportunities_config = query.include["opportunities"]
        assert opportunities_config.list_ == "Pipeline"
