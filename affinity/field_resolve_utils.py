"""Shared resolution functions for converting complex field values to text."""

from __future__ import annotations

from typing import Any


def resolve_person(value: Any) -> str | None:
    """Resolve a person field value dict to display name.

    Args:
        value: Dict with firstName/lastName keys from the V2 API.

    Returns:
        "First Last", or None if no name parts present.
    """
    if not isinstance(value, dict):
        return None
    first = value.get("firstName", "")
    last = value.get("lastName", "")
    parts = [p.strip() for p in [first, last] if isinstance(p, str) and p.strip()]
    return " ".join(parts) if parts else None


def resolve_company(value: Any) -> str | None:
    """Resolve a company field value dict to display name.

    Args:
        value: Dict with name/domain keys from the V2 API.

    Returns:
        Company name or domain, or None.
    """
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    domain = value.get("domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip()
    return None


def resolve_location(value: Any) -> str | None:
    """Resolve a location field value dict to display string.

    Args:
        value: Dict with streetAddress/city/state/country keys.

    Returns:
        Comma-separated location parts, or None.
    """
    if not isinstance(value, dict):
        return None
    parts = []
    for key in ("streetAddress", "city", "state", "country"):
        v = value.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return ", ".join(parts) if parts else None


def resolve_interaction(value: Any) -> str | None:
    """Resolve an interaction field value dict to display string.

    Args:
        value: Dict with type/subject keys.

    Returns:
        Description like "email", or None.
    """
    if not isinstance(value, dict):
        return None
    itype = value.get("type")
    if isinstance(itype, (str, int)):
        return str(itype)
    return None
