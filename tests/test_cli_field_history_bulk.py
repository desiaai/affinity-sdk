from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")

from click.testing import CliRunner

from affinity.cli.main import cli

# ---------------------------------------------------------------------------
# Validation tests (no API calls needed)
# ---------------------------------------------------------------------------


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_no_bound_rejected() -> None:
    """No --all/--max-results/--list-entry-ids with --list-id -> exit 2."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-id", "42"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    assert "bound" in result.output.lower() or "max-results" in result.output.lower()


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_list_id_and_list_entry_ids_mutual_exclusion() -> None:
    """--list-id and --list-entry-ids together -> exit 2."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history-bulk",
            "field-123",
            "--list-id",
            "42",
            "--list-entry-ids",
            "1,2,3",
            "--all",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output.lower() or "cannot" in result.output.lower()


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_list_entry_ids_with_all_rejected() -> None:
    """--list-entry-ids + --all -> exit 2."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history-bulk",
            "field-123",
            "--list-entry-ids",
            "1,2,3",
            "--all",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    assert "all" in result.output.lower()


# ---------------------------------------------------------------------------
# Functional tests (mock API)
# ---------------------------------------------------------------------------


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_list_entry_ids_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Query specific entries; entityName is null in output."""
    from affinity.models.entities import FieldValueChange

    # Build mock FieldValueChange objects matching API response format
    change_data = {
        "id": 501,
        "fieldId": "field-123",
        "entityId": 100,
        "listEntryId": 10,
        "actionType": 2,
        "value": "Won",
        "changedAt": "2024-06-01T12:00:00Z",
        "changer": {"id": 1, "type": 0, "firstName": "Alice", "lastName": "Smith"},
    }
    mock_change = FieldValueChange.model_validate(change_data)

    # Capture calls to track which entry IDs were queried
    calls: list[int] = []

    async def mock_list(
        self,  # noqa: ARG001
        field_id,  # noqa: ARG001
        *,
        list_entry_id=None,
        action_type=None,  # noqa: ARG001
        **kwargs,  # noqa: ARG001
    ):
        eid = int(list_entry_id)
        calls.append(eid)
        if eid == 10:
            return [mock_change]
        return []

    # Monkeypatch the AsyncFieldValueChangesService.list method
    from affinity.services.v1_only import AsyncFieldValueChangesService

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-entry-ids", "10,20"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    changes = payload["data"]["fieldValueChanges"]
    assert len(changes) == 1
    assert changes[0]["id"] == 501
    assert changes[0]["listEntryId"] == 10
    assert changes[0]["entityName"] is None
    assert changes[0]["actionType"] == "update"
    assert changes[0]["changerName"] == "Alice Smith"
    # Both entries should have been queried
    assert sorted(calls) == [10, 20]


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_dry_run() -> None:
    """Dry run reports estimated API calls without executing."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history-bulk",
            "field-123",
            "--list-entry-ids",
            "10,20,30",
            "--dry-run",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    dry = payload["data"]
    assert dry["dryRun"] is True
    assert dry["entries"] == 3
    assert dry["estimatedApiCalls"] == 3
    assert dry["fieldId"] == "field-123"


# ---------------------------------------------------------------------------
# Additional functional tests
# ---------------------------------------------------------------------------


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_max_results_limits_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """--max-results N with --list-id processes only N entries."""
    from affinity.cli.commands import field_cmds
    from affinity.services.lists import ListService
    from affinity.services.v1_only import AsyncFieldValueChangesService

    calls: list[int] = []

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        eid = int(list_entry_id)
        calls.append(eid)
        return []

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    # Mock list entry resolution to return 5 entries
    class FakeEntry:
        def __init__(self, eid):
            self.id = eid
            self.entity = None

    class FakeEntryService:
        def all(self):
            return [FakeEntry(i) for i in range(1, 6)]

    monkeypatch.setattr(ListService, "entries", lambda self, lid: FakeEntryService())  # noqa: ARG005

    # Also mock resolve_list_selector
    mock_resolved = MagicMock()
    mock_resolved.list.id = 42
    mock_resolved.list.name = "Pipeline"
    monkeypatch.setattr(field_cmds, "resolve_list_selector", lambda **kw: mock_resolved)  # noqa: ARG005

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-id", "42", "--max-results", "3"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    # Should have processed only 3 entries, not all 5
    assert len(calls) == 3


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_all_processes_all_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """--all processes all entries from the list."""
    from affinity.cli.commands import field_cmds
    from affinity.services.lists import ListService
    from affinity.services.v1_only import AsyncFieldValueChangesService

    calls: list[int] = []

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        calls.append(int(list_entry_id))
        return []

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    class FakeEntry:
        def __init__(self, eid):
            self.id = eid
            self.entity = None

    class FakeEntryService:
        def all(self):
            return [FakeEntry(i) for i in range(1, 6)]

    monkeypatch.setattr(ListService, "entries", lambda self, lid: FakeEntryService())  # noqa: ARG005

    mock_resolved = MagicMock()
    mock_resolved.list.id = 42
    mock_resolved.list.name = "Pipeline"
    monkeypatch.setattr(field_cmds, "resolve_list_selector", lambda **kw: mock_resolved)  # noqa: ARG005

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-id", "42", "--all"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 5  # All 5 entries processed


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_output_schema_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Output rows contain all fields from _field_value_change_payload() + entityName."""
    from affinity.models.entities import FieldValueChange
    from affinity.services.v1_only import AsyncFieldValueChangesService

    change = FieldValueChange.model_validate(
        {
            "id": 501,
            "fieldId": "field-123",
            "entityId": 100,
            "listEntryId": 10,
            "actionType": 2,
            "value": "Won",
            "changedAt": "2024-06-01T12:00:00Z",
            "changer": {"id": 1, "type": 0, "firstName": "Alice", "lastName": "Smith"},
        }
    )

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        return [change]

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-entry-ids", "10"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    row = payload["data"]["fieldValueChanges"][0]

    expected_keys = {
        "id",
        "fieldId",
        "entityId",
        "listEntryId",
        "actionType",
        "value",
        "changedAt",
        "changerName",
        "changer",
        "entityName",
    }
    assert set(row.keys()) == expected_keys


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_action_type_filter_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """--action-type is forwarded to the API call."""
    from affinity.services.v1_only import AsyncFieldValueChangesService
    from affinity.types import FieldValueChangeAction

    captured_action_types: list = []

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        captured_action_types.append(action_type)
        return []

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history-bulk",
            "field-123",
            "--list-entry-ids",
            "10",
            "--action-type",
            "update",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    assert len(captured_action_types) == 1
    assert captured_action_types[0] == FieldValueChangeAction.UPDATE


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_partial_failure_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    """One entry failing doesn't block others; failure appears as warning."""
    from affinity.models.entities import FieldValueChange
    from affinity.services.v1_only import AsyncFieldValueChangesService

    change = FieldValueChange.model_validate(
        {
            "id": 501,
            "fieldId": "field-123",
            "entityId": 100,
            "listEntryId": 10,
            "actionType": 2,
            "value": "Won",
            "changedAt": "2024-06-01T12:00:00Z",
            "changer": {"id": 1, "type": 0, "firstName": "Alice", "lastName": "Smith"},
        }
    )

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        eid = int(list_entry_id)
        if eid == 20:
            raise Exception("404 Not Found")
        return [change]

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-entry-ids", "10,20"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip())
    # Entry 10 should succeed
    assert len(payload["data"]["fieldValueChanges"]) == 1
    # Warnings should contain failure info
    warnings = payload.get("warnings", [])
    assert any("20" in w for w in warnings)
    assert any("succeeded" in w.lower() for w in warnings)


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_list_entry_ids_ignores_max_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """--list-entry-ids + --max-results: --max-results is silently ignored."""
    from affinity.services.v1_only import AsyncFieldValueChangesService

    calls: list[int] = []

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        calls.append(int(list_entry_id))
        return []

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history-bulk",
            "field-123",
            "--list-entry-ids",
            "10,20,30",
            "--max-results",
            "1",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0, result.output
    # All 3 entries should be processed despite --max-results 1
    assert sorted(calls) == [10, 20, 30]


@pytest.mark.req("CLI-FIELD-HISTORY-BULK")
def test_concurrency_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """XAFFINITY_CONCURRENCY env var controls concurrency."""
    from affinity.cli.query.executor import RateLimitedExecutor
    from affinity.services.v1_only import AsyncFieldValueChangesService

    captured_concurrency: list[int] = []
    original_init = RateLimitedExecutor.__init__

    def tracking_init(self, concurrency=15):
        captured_concurrency.append(concurrency)
        original_init(self, concurrency)

    monkeypatch.setattr(RateLimitedExecutor, "__init__", tracking_init)

    async def mock_list(self, field_id, *, list_entry_id=None, action_type=None, **kwargs):  # noqa: ARG001
        return []

    monkeypatch.setattr(AsyncFieldValueChangesService, "list", mock_list)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history-bulk", "field-123", "--list-entry-ids", "10"],
        env={"AFFINITY_API_KEY": "test-key", "XAFFINITY_CONCURRENCY": "5"},
    )
    assert result.exit_code == 0, result.output
    assert 5 in captured_concurrency
