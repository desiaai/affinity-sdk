# Filter Operators Reference

Complete reference for all filter operators in the Affinity query language.

## Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equal | `{"path": "status", "op": "eq", "value": "Active"}` |
| `neq` | Not equal | `{"path": "status", "op": "neq", "value": "Closed"}` |
| `gt` | Greater than | `{"path": "amount", "op": "gt", "value": 10000}` |
| `gte` | Greater than or equal | `{"path": "amount", "op": "gte", "value": 10000}` |
| `lt` | Less than | `{"path": "amount", "op": "lt", "value": 5000}` |
| `lte` | Less than or equal | `{"path": "amount", "op": "lte", "value": 5000}` |

## String Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `contains` | Contains substring (case-insensitive) | `{"path": "email", "op": "contains", "value": "@gmail"}` |
| `starts_with` | Starts with (case-insensitive) | `{"path": "name", "op": "starts_with", "value": "Acme"}` |
| `ends_with` | Ends with (case-insensitive) | `{"path": "email", "op": "ends_with", "value": "@acme.com"}` |

## Collection Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `in` | Value in list | `{"path": "status", "op": "in", "value": ["New", "Active"]}` |
| `between` | Value in range | `{"path": "amount", "op": "between", "value": [1000, 5000]}` |
| `contains_any` | String contains any substring (case-insensitive) | `{"path": "bio", "op": "contains_any", "value": ["python", "java"]}` |
| `contains_all` | String contains all substrings (case-insensitive) | `{"path": "bio", "op": "contains_all", "value": ["senior", "engineer"]}` |
| `has_any` | Array field contains any of the values | `{"path": "fields.Team Member", "op": "has_any", "value": ["LB", "MA"]}` |
| `has_all` | Array field contains all of the values | `{"path": "fields.Team Member", "op": "has_all", "value": ["LB", "MA"]}` |

## Null/Empty Checks

| Operator | Description | Example |
|----------|-------------|---------|
| `is_null` | Field is null or empty string | `{"path": "email", "op": "is_null"}` |
| `is_not_null` | Field is not null and not empty | `{"path": "email", "op": "is_not_null"}` |
| `is_empty` | Field is null, empty string, or empty array | `{"path": "emails", "op": "is_empty"}` |

## Multi-Select Field Filtering

Multi-select dropdown fields (like "Team Member") return arrays. Operators handle these automatically:

| Operator | Single-value field | Multi-select field |
|----------|-------------------|-------------------|
| `eq` | Exact match | Scalar: membership check / List: set equality |
| `neq` | Not equal | Scalar: not in array / List: set inequality |
| `in` | Value in list | Any intersection between arrays |
| `has_any` | Returns false | Any specified value present |
| `has_all` | Returns false | All specified values present |

```json
// Find entries where Team Member includes "LB"
{ "path": "fields.Team Member", "op": "eq", "value": "LB" }

// Find entries where Team Member includes any of ["LB", "DW"]
{ "path": "fields.Team Member", "op": "has_any", "value": ["LB", "DW"] }

// Find entries where Team Member includes both "LB" and "MA"
{ "path": "fields.Team Member", "op": "has_all", "value": ["LB", "MA"] }
```

## Date Filtering

### Relative Dates

```json
{"path": "created_at", "op": "gte", "value": "-30d"}
```

Supported formats:
- `-30d` — 30 days ago
- `+7d` — 7 days from now
- `today` — start of today
- `now` — current time
- `yesterday` — start of yesterday
- `tomorrow` — start of tomorrow

## Field Paths

Access nested fields using dot notation:

```json
{"path": "fields.Status", "op": "eq", "value": "Active"}
```

Common paths:
- `fields.<FieldName>` — custom list fields on listEntries (preferred)
- `fields.*` — all custom fields (avoid for lists with 50+ fields — very slow)
- `emails[0]` — first email in array
- `company.name` — nested object field (on included relationships)
