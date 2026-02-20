from __future__ import annotations

import json

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")

try:
    import respx
except ModuleNotFoundError:  # pragma: no cover
    respx = None  # type: ignore[assignment]

from click.testing import CliRunner
from httpx import Response

from affinity.cli.main import cli

if respx is None:  # pragma: no cover
    pytest.skip("respx is not installed", allow_module_level=True)


def test_field_history_by_person_id(respx_mock: respx.MockRouter) -> None:
    """List field value changes for a person."""
    # V1 API returns bare array with camelCase keys
    # HTTPClient normalizes to {"data": [...]} internally
    respx_mock.get("https://api.affinity.co/field-value-changes").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": 101,
                    "fieldId": "field-123",  # camelCase, string format
                    "entityId": 456,
                    "listEntryId": None,
                    "actionType": 2,
                    "value": "Closed",
                    "changedAt": "2024-01-15T10:30:00Z",
                    "changer": {"id": 10, "type": 0, "firstName": "Jane", "lastName": "Doe"},
                }
            ],
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history", "field-123", "--person-id", "456"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    changes = payload["data"]["fieldValueChanges"]
    assert len(changes) == 1
    assert changes[0]["id"] == 101
    assert changes[0]["fieldId"] == "field-123"
    # Enum displayed as name, not integer
    assert changes[0]["actionType"] == "update"
    # Changer name flattened for table display
    assert changes[0]["changerName"] == "Jane Doe"


def test_field_history_by_company_id(respx_mock: respx.MockRouter) -> None:
    """List field value changes for a company."""
    respx_mock.get("https://api.affinity.co/field-value-changes").mock(
        return_value=Response(200, json=[])
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history", "field-123", "--company-id", "789"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["data"]["fieldValueChanges"] == []


def test_field_history_with_action_type_filter(respx_mock: respx.MockRouter) -> None:
    """Filter field value changes by action type."""
    respx_mock.get("https://api.affinity.co/field-value-changes").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": 102,
                    "fieldId": "field-123",
                    "entityId": 456,
                    "listEntryId": None,
                    "actionType": 0,
                    "value": "Open",
                    "changedAt": "2024-01-10T09:00:00Z",
                }
            ],
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--json",
            "field",
            "history",
            "field-123",
            "--person-id",
            "456",
            "--action-type",
            "create",
        ],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["data"]["fieldValueChanges"][0]["actionType"] == "create"


def test_field_history_with_max_results(respx_mock: respx.MockRouter) -> None:
    """Client-side max-results limiting."""
    respx_mock.get("https://api.affinity.co/field-value-changes").mock(
        return_value=Response(
            200,
            json=[
                {
                    "id": 1,
                    "fieldId": "field-123",
                    "entityId": 456,
                    "listEntryId": None,
                    "actionType": 2,
                    "value": "A",
                    "changedAt": "2024-01-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "fieldId": "field-123",
                    "entityId": 456,
                    "listEntryId": None,
                    "actionType": 2,
                    "value": "B",
                    "changedAt": "2024-01-02T00:00:00Z",
                },
                {
                    "id": 3,
                    "fieldId": "field-123",
                    "entityId": 456,
                    "listEntryId": None,
                    "actionType": 2,
                    "value": "C",
                    "changedAt": "2024-01-03T00:00:00Z",
                },
            ],
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "history", "field-123", "--person-id", "456", "--max-results", "2"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert len(payload["data"]["fieldValueChanges"]) == 2


def test_field_history_requires_exactly_one_selector() -> None:
    """Error when no entity selector or multiple selectors provided."""
    runner = CliRunner()

    # No selector
    result = runner.invoke(
        cli,
        ["--json", "field", "history", "field-123"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    assert "exactly one" in result.output.lower()

    # Multiple selectors
    result = runner.invoke(
        cli,
        ["--json", "field", "history", "field-123", "--person-id", "1", "--company-id", "2"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    assert "only one" in result.output.lower()


@pytest.mark.req("CLI-FIELD-LS-LIST-ALIAS")
def test_field_ls_list_alias(respx_mock: respx.MockRouter) -> None:
    """--list alias works identically to --list-id on field ls."""
    respx_mock.get("https://api.affinity.co/fields").mock(return_value=Response(200, json=[]))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "field", "ls", "--list", "Pipeline"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    # Should not fail with "No such option: --list"
    assert "No such option" not in (result.output + str(result.exception or ""))


def test_field_history_missing_field_id() -> None:
    """Error when FIELD_ID argument is missing."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["field", "history", "--person-id", "456"],
        env={"AFFINITY_API_KEY": "test-key"},
    )
    assert result.exit_code == 2
    # Click reports missing argument
    assert "field_id" in result.output.lower() or "missing argument" in result.output.lower()
