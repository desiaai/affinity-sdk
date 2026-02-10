"""Output formatters for CLI commands.

Provides unified formatting for all output types:
- JSON: Full structured output (preserves CommandResult envelope)
- JSONL: One JSON object per line (streaming-friendly, data-only)
- Markdown: GitHub-flavored markdown tables (data-only)
- TOON: Token-Optimized Object Notation (data-only)
- CSV: Comma-separated values (data-only)
- Table: Rich terminal tables (existing, delegates to render.py)

TOON is an open specification designed for LLM token efficiency.
See: https://github.com/toon-format/spec/blob/main/SPEC.md
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from typing import Any, Literal

OutputFormat = Literal["table", "json", "jsonl", "markdown", "toon", "csv"]


def to_cell(value: Any) -> str:
    """Convert value to string for tabular output.

    This is the canonical implementation used by all formatters.
    Handles various nested structures for human readability:
    - Dropdown fields: extracts "text" value
    - Person entities: "firstName lastName (id=N)"
    - Company entities: "name (id=N)"
    - Fields containers: "Field1=val, Field2=val... (N fields)"
    - Other dicts: "object (N keys)"
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # For multi-select fields, extract text if available
        texts = []
        for v in value:
            if isinstance(v, dict) and "text" in v:
                texts.append(str(v["text"]))
            elif v is not None:
                texts.append(to_cell(v))
        return "; ".join(texts)
    if isinstance(value, dict):
        # For dropdown fields, extract text if available
        if "text" in value:
            return str(value["text"])

        # Check for typed entities (person/company)
        # Person entities have firstName/lastName (type can be "external", "internal", or absent)
        entity_id = value.get("id")
        entity_type = value.get("type")

        # Detect person by firstName/lastName keys OR by person-related type
        is_person = ("firstName" in value or "lastName" in value) or entity_type in (
            "person",
            "external",
            "internal",
        )
        if is_person:
            name = _extract_person_name(value)
            if name and entity_id is not None:
                return f"{name} (id={entity_id})"
            elif name:
                return name
            elif entity_id is not None:
                return f"person (id={entity_id})"

        if entity_type == "company":
            name = value.get("name") or value.get("domain")
            if name and entity_id is not None:
                return f"{name} (id={entity_id})"
            elif name:
                return str(name)
            elif entity_id is not None:
                return f"company (id={entity_id})"

        # Check for fields container (raw API format with "data" dict)
        if "data" in value and isinstance(value.get("data"), dict):
            preview = _extract_fields_preview(value["data"])
            count = len(value["data"])
            if preview and count > 0:
                return f"{preview}... ({count} fields)"
            elif count > 0:
                return f"({count} fields)"

        # Generic dict with name (or entityName for list export format)
        name = value.get("name") or value.get("entityName")
        if isinstance(name, str) and name.strip():
            # Include entityId if available for drill-down
            entity_id = value.get("entityId")
            if entity_id is not None:
                return f"{name} (id={entity_id})"
            return name

        # Check for normalized fields dict (query executor format: {"FieldName": value, ...})
        # Only if no common keys that indicate a different structure
        if _is_flat_fields_dict(value):
            preview = _extract_flat_fields_preview(value)
            count = len(value)
            if preview:
                # Only show count when truncated (more than 2 fields shown)
                if count > 2:
                    return f"{preview}... ({count} fields)"
                return preview
            elif count > 0:
                return f"({count} fields)"

        # Fallback: compact placeholder
        return f"object ({len(value)} keys)"
    return str(value)


def _extract_person_name(value: dict[str, Any]) -> str | None:
    """Extract display name from a person entity."""
    from affinity.field_resolve_utils import resolve_person

    return resolve_person(value)


def _extract_fields_preview(data: dict[str, Any], max_fields: int = 2) -> str | None:
    """Extract a preview of field values from a fields data dict.

    The fields data structure is:
        {"field-abc": {"name": "Status", "value": {"data": {"text": "Active"}}}, ...}

    Returns something like: "Status=Active, Owner=Jane"
    """
    previews: list[str] = []
    for field_obj in data.values():
        if len(previews) >= max_fields:
            break
        if not isinstance(field_obj, dict):
            continue

        field_name = field_obj.get("name")
        if not isinstance(field_name, str) or not field_name.strip():
            continue

        # Extract the value - could be nested in value.data
        value_wrapper = field_obj.get("value")
        display_value: str | None = None

        if isinstance(value_wrapper, dict):
            inner_data = value_wrapper.get("data")
            if isinstance(inner_data, dict):
                # Dropdown: {"text": "Active"}
                if "text" in inner_data:
                    display_value = str(inner_data["text"])
                # Person reference: {"firstName": "Jane", "lastName": "Doe"}
                elif "firstName" in inner_data or "lastName" in inner_data:
                    display_value = _extract_person_name(inner_data)
                # Company reference: {"name": "Acme"}
                elif "name" in inner_data:
                    display_value = str(inner_data["name"])
            elif inner_data is not None:
                # Simple value (string, number)
                display_value = str(inner_data)
        elif value_wrapper is not None:
            display_value = str(value_wrapper)

        if display_value:
            previews.append(f"{field_name}={display_value}")

    return ", ".join(previews) if previews else None


def _is_flat_fields_dict(value: dict[str, Any]) -> bool:
    """Check if a dict looks like normalized fields (flat key-value pairs).

    Normalized fields from the query executor look like:
        {"Team Member": "LB", "Status": "Active", "Deal Size": 1000000}

    Multi-select fields may have list values:
        {"Team Member": ["LB", "JD"], "Status": "Active"}

    Returns True if:
    - Has no common structural keys (id, type, name, data, etc.)
    - All values are simple types (str, int, float, bool, None), dropdown dicts, or lists thereof
    """
    if not value:
        return False

    # Common keys that indicate this is NOT a fields dict
    common_keys = {
        "id",
        "type",
        "name",
        "data",
        "text",  # Entity/structure keys
        "entityId",
        "entityName",
        "entityType",
        "listEntryId",  # List export keys
        "firstName",
        "lastName",
        "domain",
        "domains",  # Person/company keys
        "city",
        "state",
        "country",
        "zip",
        "street",  # Location keys
        "pagination",
        "requested",
        "nextCursor",  # API response keys
    }

    # If it has any common key, it's not a flat fields dict
    if value.keys() & common_keys:
        return False

    for v in value.values():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            continue
        if isinstance(v, dict) and "text" in v:
            continue
        # Check for list of simple values (multi-select fields)
        if isinstance(v, list) and all(
            item is None
            or isinstance(item, (str, int, float, bool))
            or (isinstance(item, dict) and "text" in item)
            for item in v
        ):
            continue
        # Has complex nested value - not a flat fields dict
        return False
    return True


def _extract_flat_fields_preview(value: dict[str, Any], max_fields: int = 2) -> str | None:
    """Extract preview from a flat fields dict.

    Args:
        value: Dict like {"Team Member": "LB", "Status": "Active"}
               or with lists: {"Team Member": ["LB", "JD"], "Status": "Active"}
        max_fields: Maximum number of fields to show

    Returns:
        Preview string like "Team Member=LB, Status=Active"
        or "Team Member=LB; JD, Status=Active" for multi-select
    """
    previews: list[str] = []
    for field_name, field_value in value.items():
        if len(previews) >= max_fields:
            break

        if field_value is None:
            continue

        # Extract display value
        if isinstance(field_value, list):
            # Multi-select field: join values with semicolons
            parts = []
            for item in field_value:
                if item is None:
                    continue
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                elif isinstance(item, bool):
                    parts.append("true" if item else "false")
                else:
                    parts.append(str(item))
            display = "; ".join(parts) if parts else ""
        elif isinstance(field_value, dict) and "text" in field_value:
            display = str(field_value["text"])
        elif isinstance(field_value, bool):
            display = "true" if field_value else "false"
        else:
            display = str(field_value)

        if display:
            previews.append(f"{field_name}={display}")

    return ", ".join(previews) if previews else None


def format_data(
    data: list[dict[str, Any]],
    format: OutputFormat,
    *,
    fieldnames: list[str] | None = None,
    pretty: bool = False,
) -> str:
    """Format tabular data in the specified output format.

    This formats the DATA portion only, not the full CommandResult envelope.

    Args:
        data: List of row dictionaries
        format: Output format
        fieldnames: Column order (auto-detected from first row if None)
        pretty: Pretty-print where applicable (JSON only)

    Returns:
        Formatted string

    Raises:
        ValueError: If format is "table" (use render.py instead)
    """
    if format == "table":
        raise ValueError("Use render.py for table format")

    if not data:
        return _empty_output(format, fieldnames)

    fieldnames = fieldnames or list(data[0].keys())

    match format:
        case "json":
            return format_json_data(data, pretty=pretty)
        case "jsonl":
            return format_jsonl(data)
        case "markdown":
            return format_markdown(data, fieldnames)
        case "toon":
            return format_toon(data, fieldnames)
        case "csv":
            return format_csv(data, fieldnames)
        case _:
            raise ValueError(f"Unknown format: {format}")


def format_json_data(data: list[dict[str, Any]], *, pretty: bool = False) -> str:
    """Format as JSON array (data only, no envelope)."""
    indent = 2 if pretty else None
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def format_jsonl(data: list[dict[str, Any]]) -> str:
    """Format as JSON Lines (one object per line).

    Standard: https://jsonlines.org/

    Requirements:
    - Each line is a valid JSON value (typically object)
    - Lines separated by \\n (\\r\\n also acceptable)
    - UTF-8 encoding, no BOM
    - Trailing newline recommended for file concatenation
    """
    if not data:
        return ""
    lines = [json.dumps(row, default=str, ensure_ascii=False) for row in data]
    return "\n".join(lines) + "\n"  # Trailing newline per spec recommendation


def format_markdown(data: list[dict[str, Any]], fieldnames: list[str]) -> str:
    """Format as GitHub-flavored Markdown table.

    Features:
    - Numeric columns are right-aligned
    - Pipe characters escaped
    - Newlines converted to <br>
    """
    if not data:
        return "_No results_"

    # Detect numeric columns for alignment
    numeric_cols = _detect_numeric_columns(data, fieldnames)

    # Header row
    header = "| " + " | ".join(fieldnames) + " |"

    # Separator row with alignment
    separators = []
    for f in fieldnames:
        if f in numeric_cols:
            separators.append("---:")  # Right-align numbers
        else:
            separators.append("---")
    separator = "| " + " | ".join(separators) + " |"

    # Data rows
    rows = []
    for row in data:
        cells = [_md_escape(to_cell(row.get(f))) for f in fieldnames]
        rows.append("| " + " | ".join(cells) + " |")

    return "\n".join([header, separator, *rows])


def format_toon(data: list[dict[str, Any]], fieldnames: list[str]) -> str:
    """Format as TOON (Token-Optimized Object Notation).

    TOON is an open specification for LLM-optimized data serialization.
    Spec: https://github.com/toon-format/spec/blob/main/SPEC.md

    For uniform object arrays (our use case), TOON uses tabular format:
        [N]{field1,field2,field3}:
          value1,value2,value3
          value4,value5,value6

    Note: Rows are indented by 2 spaces (TOON spec §12).

    Benefits:
    - 30-60% fewer tokens than JSON for tabular data
    - Schema-aware (field names declared once)
    - Lossless JSON round-trip
    - Row count enables truncation detection

    Trade-offs:
    - Less effective for non-uniform/nested structures
    - Most LLMs lack explicit TOON training data
    """
    if not data:
        return "[0]{}:"

    # TOON root-level tabular array format: [count]{fields}:
    header = f"[{len(data)}]{{{','.join(fieldnames)}}}:"

    lines = [header]
    for row in data:
        cells = []
        for f in fieldnames:
            val = row.get(f)
            # Numbers are emitted directly without quoting in TOON
            if isinstance(val, bool):
                cells.append("true" if val else "false")
            elif isinstance(val, (int, float)):
                cells.append(str(val))
            else:
                cells.append(_toon_quote(to_cell(val)))
        # Rows indented by 2 spaces per TOON spec
        lines.append("  " + ",".join(cells))

    return "\n".join(lines)


def format_csv(data: list[dict[str, Any]], fieldnames: list[str]) -> str:
    """Format as CSV string.

    Always includes header row, even for empty data (when fieldnames provided).
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in data:
        # Use fieldnames to ensure consistent column order
        writer.writerow({f: to_cell(row.get(f)) for f in fieldnames})
    return output.getvalue()


def _detect_numeric_columns(data: list[dict[str, Any]], fieldnames: list[str]) -> set[str]:
    """Detect columns that contain numeric values for right-alignment.

    Design decision: Requires ALL non-null values to be numeric.
    A threshold approach (e.g., >80% numeric) was considered but rejected
    because mixed-type columns are rare in our data model, and strict
    detection avoids surprising alignment for edge cases.
    """
    numeric = set()
    for f in fieldnames:
        values = [row.get(f) for row in data if row.get(f) is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
            numeric.add(f)
    return numeric


def _md_escape(text: str) -> str:
    """Escape special markdown characters in table cells."""
    # Escape pipe characters (table delimiter)
    text = text.replace("|", "\\|")
    # Replace newlines with <br> for multi-line content
    text = text.replace("\n", "<br>")
    return text


def _toon_quote(text: str) -> str:
    """Quote TOON string values per spec §7.

    TOON spec: strings MUST be quoted if they:
    - Are empty
    - Have leading/trailing whitespace
    - Equal true, false, null (case-sensitive)
    - Match numeric patterns
    - Contain: colon, quote, backslash, brackets, control chars, delimiter
    - Equal "-" or start with hyphen

    Valid escapes: \\\\ \" \\n \\r \\t
    """
    # Empty string must be quoted
    if not text:
        return '""'

    # Check if quoting needed
    needs_quotes = (
        text != text.strip()  # leading/trailing whitespace
        or text in ("true", "false", "null")  # reserved words (case-sensitive)
        or text == "-"
        or text.startswith("-")  # hyphen rules
        or re.match(r"^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$", text, re.I)  # numeric
        or re.match(r"^0\d+$", text)  # octal-like
        or any(c in text for c in ':"\\[]{}')  # special chars
        or any(ord(c) < 32 for c in text)  # control chars
        or "," in text  # delimiter
    )

    if not needs_quotes:
        return text

    # Apply escaping per spec §7.1
    escaped = text
    escaped = escaped.replace("\\", "\\\\")  # backslash first
    escaped = escaped.replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("\r", "\\r")
    escaped = escaped.replace("\t", "\\t")

    return f'"{escaped}"'


def _toon_number(value: int | float) -> str:
    """Format number per TOON canonical form (spec §3, §4.5).

    Rules:
    - NaN and ±Infinity normalize to null (spec §3)
    - No exponent notation (1000000 not 1e6)
    - Integer form if no fractional part (1 not 1.0)
    - -0 normalizes to 0
    """
    if isinstance(value, float):
        # NaN and Infinity normalize to null (spec §3)
        if math.isnan(value) or math.isinf(value):
            return "null"
        if value == 0.0:
            return "0"  # Handles -0.0 → "0"
        if value.is_integer():
            return str(int(value))  # 1.0 → "1"
    return str(value)


def _toon_cell(value: Any) -> str:
    """Format value for TABULAR context (inside data rows).

    Used for: data rows, included entity rows.
    Numbers and booleans are unquoted literals in TOON.
    """
    if value is None:
        return "null"  # TOON spec: null literal for null values
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _toon_number(value)
    # Everything else goes through to_cell() for string conversion, then quoting
    return _toon_quote(to_cell(value))


def _toon_primitive(value: Any) -> str:
    """Format value for KEY-VALUE context (pagination, non-tabular sections).

    Used for: pagination section, metadata sections.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _toon_number(value)
    if isinstance(value, str):
        return _toon_quote(value)
    # Nested structures (list, dict): fall back to compact JSON
    return _toon_quote(json.dumps(value, separators=(",", ":")))


def format_toon_envelope(
    data: list[dict[str, Any]],
    fieldnames: list[str],
    *,
    pagination: dict[str, Any] | None = None,
    included: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Format full query result envelope as TOON.

    TOON supports root-level objects with multiple keys.
    This preserves all envelope data while being token-efficient.

    Args:
        data: List of data records
        fieldnames: Column names for the data section
        pagination: Pagination info (hasMore, total, nextUrl, etc.)
        included: Included entities by type (companies, persons, etc.)

    Returns:
        TOON-formatted string with data, pagination, and included sections
    """
    lines = []

    # Data section (tabular)
    lines.append(f"data[{len(data)}]{{{','.join(fieldnames)}}}:")
    for row in data:
        cells = [_toon_cell(row.get(f)) for f in fieldnames]
        lines.append("  " + ",".join(cells))

    # Pagination section (if present) - flat key-value pairs
    if pagination:
        lines.append("pagination:")
        for key, value in pagination.items():
            lines.append(f"  {key}: {_toon_primitive(value)}")

    # Included section - each entity type as a separate tabular array at root level
    # (Not nested under "included:" - TOON spec prefers flat structure)
    if included:
        for entity_type, entities in included.items():
            if entities:
                # Use union of all keys (entities may have different fields)
                # Note: Fields appear in first-seen order. This is intentional - sorting
                # would be surprising since common fields (id, name) often appear first.
                entity_fields = list(dict.fromkeys(k for e in entities for k in e))
                lines.append(
                    f"included_{entity_type}[{len(entities)}]{{{','.join(entity_fields)}}}:"
                )
                for entity in entities:
                    cells = [_toon_cell(entity.get(f)) for f in entity_fields]
                    lines.append("  " + ",".join(cells))

    return "\n".join(lines)


def _empty_output(format: OutputFormat, fieldnames: list[str] | None = None) -> str:
    """Return appropriate empty output for format.

    For tabular formats (markdown, csv), includes headers when fieldnames known.
    This provides consistent structure even with empty results.
    """
    match format:
        case "json":
            return "[]"
        case "jsonl":
            return ""  # Empty is valid JSONL
        case "markdown":
            # Return header-only table when fieldnames known (consistent with CSV)
            if fieldnames:
                header = "| " + " | ".join(fieldnames) + " |"
                separator = "| " + " | ".join(["---"] * len(fieldnames)) + " |"
                return f"{header}\n{separator}"
            return "_No results_"
        case "toon":
            # Include field names in empty output when known
            if fieldnames:
                return f"[0]{{{','.join(fieldnames)}}}:"
            return "[0]{}:"
        case "csv":
            # Include header even with no data (when fieldnames known)
            if fieldnames:
                return ",".join(fieldnames) + "\n"
            return ""
        case _:
            return ""
