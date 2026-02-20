from __future__ import annotations

import json

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
