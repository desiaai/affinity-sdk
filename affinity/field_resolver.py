"""Field resolution utilities for extracting values by name."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

__all__ = ["FieldResolver"]

if TYPE_CHECKING:
    from .models.entities import (
        Company,
        FieldMetadata,
        ListEntryWithEntity,
        Opportunity,
        Person,
    )
    from .models.types import AnyFieldId


class FieldResolver:
    """
    Helper for extracting field values by name from entities.

    Caches field metadata internally for efficient repeated lookups.

    Example:
        >>> # Fetch field metadata once
        >>> resolver = FieldResolver(client.companies.get_fields())
        >>>
        >>> # Use throughout your code
        >>> for company in companies:
        ...     status = resolver.get(company, "Status")
        ...     industry = resolver.get(company, "Industry")
        ...     print(f"{company.name}: {status}, {industry}")
    """

    def __init__(self, fields: Sequence[FieldMetadata]) -> None:
        """
        Create a resolver from field metadata.

        Args:
            fields: Field metadata from client.companies.get_fields(),
                    client.persons.get_fields(), etc.
        """
        # Build case-insensitive name -> field mapping
        self._by_name: dict[str, FieldMetadata] = {}
        self._by_id: dict[str, FieldMetadata] = {}
        self._dropdown_options: dict[int, str] = {}  # option_id -> text

        for field in fields:
            name_key = field.name.casefold()
            if name_key in self._by_name:
                existing = self._by_name[name_key]
                src_existing = existing.enrichment_source or existing.type or "unknown"
                src_new = field.enrichment_source or field.type or "unknown"
                warnings.warn(
                    f"Duplicate field name '{field.name}' "
                    f"({src_existing} [{existing.id}] vs {src_new} [{field.id}]). "
                    f"Later field will be used. Use get_by_id() for unambiguous access.",
                    UserWarning,
                    stacklevel=2,
                )
            self._by_name[name_key] = field
            self._by_id[str(field.id)] = field
            if field.dropdown_options:
                for option in field.dropdown_options:
                    self._dropdown_options[int(option.id)] = option.text

    def get(
        self,
        entity: Company | Person | Opportunity | ListEntryWithEntity,
        field_name: str,
        *,
        resolve_dropdowns: bool = False,
    ) -> Any:
        """
        Get a field value by name from an entity.

        Args:
            entity: The entity (Company, Person, Opportunity, or ListEntry)
            field_name: The field display name (case-insensitive)
            resolve_dropdowns: If True, return dropdown option text instead of ID

        Returns:
            The extracted field value, or None if field not found or not populated.

        Example:
            >>> status = resolver.get(company, "Status")
            >>> print(status)  # "Active"

            >>> # With dropdown resolution
            >>> stage = resolver.get(opportunity, "Stage", resolve_dropdowns=True)
            >>> print(stage)  # "Negotiation" instead of 12345
        """
        if not entity.fields.requested:
            warnings.warn(
                "Fields were not requested for this entity. "
                "Pass field_ids or field_types when fetching to populate field values.",
                UserWarning,
                stacklevel=2,
            )
            return None

        field = self._by_name.get(field_name.casefold())
        if field is None:
            return None

        value = entity.fields.get_value(str(field.id))

        if resolve_dropdowns and value is not None:
            value = self._resolve_dropdown(value)

        return value

    def get_many(
        self,
        entity: Company | Person | Opportunity | ListEntryWithEntity,
        field_names: Sequence[str],
        *,
        resolve_dropdowns: bool = False,
    ) -> dict[str, Any]:
        """
        Get multiple field values by name.

        Args:
            entity: The entity (Company, Person, Opportunity, or ListEntry)
            field_names: List of field names to extract
            resolve_dropdowns: If True, resolve dropdown IDs to text

        Returns:
            Dict mapping field_name -> value (None for missing/unpopulated fields)

        Example:
            >>> values = resolver.get_many(company, ["Status", "Industry", "Size"])
            >>> print(values)
            {'Status': 'Active', 'Industry': 'Tech', 'Size': None}
        """
        return {
            name: self.get(entity, name, resolve_dropdowns=resolve_dropdowns)
            for name in field_names
        }

    def _resolve_dropdown(self, value: Any) -> Any:
        """Resolve dropdown option ID(s) to text."""
        if isinstance(value, list):
            return [self._resolve_dropdown(v) for v in value]
        if isinstance(value, int) and value in self._dropdown_options:
            return self._dropdown_options[value]
        return value

    def get_by_id(
        self,
        entity: Company | Person | Opportunity | ListEntryWithEntity,
        field_id: str | AnyFieldId,
        *,
        resolve_dropdowns: bool = False,
    ) -> Any:
        """
        Get a field value by ID (unambiguous, for duplicate field names).

        Args:
            entity: The entity
            field_id: The field ID (e.g., "field-123" or FieldId(123))
            resolve_dropdowns: If True, resolve dropdown IDs to text

        Returns:
            The extracted field value, or None if not found.
        """
        value = entity.fields.get_value(str(field_id))
        if resolve_dropdowns and value is not None:
            value = self._resolve_dropdown(value)
        return value

    def field_names(self) -> list[str]:
        """Get all available field names."""
        return [f.name for f in self._by_name.values()]

    def has_field(self, field_name: str) -> bool:
        """Check if a field exists by name."""
        return field_name.casefold() in self._by_name
