from __future__ import annotations

import pytest

pytest.importorskip("rich_click")
pytest.importorskip("rich")
pytest.importorskip("platformdirs")

from affinity.cli.context import _hint_for_validation_message


@pytest.mark.req("CLI-INTERACTION-INCLUDE-ME")
class TestInteractionValidationHint:
    """Tests for interaction-related validation error hints."""

    def test_hint_for_person_ids_validation(self) -> None:
        msg = "person_ids must include at least one internal and one external person"
        hint = _hint_for_validation_message(msg)
        assert hint is not None
        assert "internal" in hint.lower()
        assert "whoami" in hint.lower()

    def test_hint_for_person_ids_internal_only(self) -> None:
        msg = "person_ids must include at least one internal person"
        hint = _hint_for_validation_message(msg)
        assert hint is not None
        assert "internal" in hint.lower()

    def test_hint_for_not_null_data_error(self) -> None:
        """The actual error message from the Cowork audit — too generic to match."""
        msg = "validation_error: value at /value/data is not null"
        hint = _hint_for_validation_message(msg)
        assert hint is None  # Generic validation error, not interaction-specific

    def test_hint_does_not_match_unrelated_person_message(self) -> None:
        msg = "person_id 999 not found"
        hint = _hint_for_validation_message(msg)
        # Should NOT match the interaction hint (this is a different error pattern)
        assert hint is None or "internal" not in hint.lower()

    def test_existing_date_range_hint_preserved(self) -> None:
        msg = "Date range must be within 1 year"
        hint = _hint_for_validation_message(msg)
        assert hint is not None
        assert "1 year" in hint
