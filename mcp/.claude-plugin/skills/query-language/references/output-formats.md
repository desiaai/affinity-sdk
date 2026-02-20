# Output Formats & Pagination Reference

## Format Parameter

| Format | Token Efficiency | Best For | Description |
|--------|-----------------|----------|-------------|
| `toon` | **High (~40% fewer)** | **Default** — large datasets | Full envelope with `data`, `pagination`, `included` |
| `json` | Low | Programmatic use | Full JSON structure (same data as TOON) |
| `markdown` | Medium-High | **LLM analysis** | GitHub-flavored table + pagination footer |
| `jsonl` | Medium | Streaming | One JSON object per line (data only) |
| `csv` | Medium | Spreadsheets | Comma-separated values (data only) |

### Recommendations

- **For LLM analysis tasks**: Use `markdown` — LLMs are trained on documentation and tables
- **For large result sets**: Use `toon` to minimize tokens (30-60% smaller than JSON)
- **For programmatic processing**: Use `json` for full structure
- **For streaming workflows**: Use `jsonl` for line-by-line processing

### Format Examples

**JSON:**
```json
{"data": [{"id": 1, "name": "Acme"}], "included": {...}, "pagination": {...}}
```

**JSONL:**
```jsonl
{"id": 1, "name": "Acme"}
{"id": 2, "name": "Beta"}
```

**Markdown:**
```markdown
| id | name |
| --- | --- |
| 1 | Acme |
| 2 | Beta |
```

**TOON (default):**
```
data[2]{id,name}:
  1,Acme
  2,Beta
pagination:
  hasMore: false
  total: 2
```

**Note:** `jsonl` and `csv` are data-only export formats (no envelope). `toon`, `json`, and `markdown` preserve pagination and included entity information.

## Tool Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | object | required | The JSON query object |
| `dryRun` | boolean | false | Preview execution plan without running |
| `maxRecords` | integer | 1000 | Safety limit (max 10000) |
| `timeout` | integer | auto | Query timeout in seconds (auto-calculated from estimated API calls) |
| `maxOutputBytes` | integer | 50000 | Truncation limit for results |
| `format` | string | "toon" | Output format |
| `cursor` | string | null | Resume from previous truncated response |

### Timeout Auto-Calculation

When `timeout` is not specified, it's automatically calculated based on estimated API calls:
- **Formula**: ~2 seconds per API call, minimum 30 seconds
- **Example**: Query with 100 API calls -> 200 second timeout

## Truncated Responses & Cursor Pagination

When output exceeds `maxOutputBytes`, the response includes `truncated: true` and a `nextCursor`:

```json
{
  "data": [...],
  "truncated": true,
  "nextCursor": "eyJ2IjoxLC...",
  "_cursorMode": "streaming"
}
```

Resume with cursor (keep query and format identical):

```json
{
  "query": {"from": "persons", "limit": 1000},
  "format": "toon",
  "cursor": "eyJ2IjoxLC..."
}
```

**Important**: The `nextCursor` is for **output size truncation**, not record limits. A query returning all requested records won't have a `nextCursor` unless the output was too large.

### Cursor Modes

- **Streaming**: Simple queries without `orderBy`/`aggregate`/`groupBy` — O(1) resumption via API cursor
- **Full-fetch**: Complex queries with `orderBy`/`aggregate`/`groupBy` — results cached for 1 hour

**Rules:**
- NEVER fabricate cursors (cryptographically validated)
- Query and format MUST match exactly when resuming
- Cursors expire after 1 hour

### TOON Format Truncation

```
data[56]{id,name}:
  ...
truncated: true
nextCursor: eyJ2IjoxLCJxaCI6IjZmYzJhZDJkYTI5...
_cursorMode: streaming
```

## `list export` Output Format

The `list export` command uses a different JSON structure than `query`:

```json
{
  "data": {
    "rows": [
      {"listEntryId": 123, "entityType": "company", "entityId": 456,
       "entityName": "Acme", "Status": "Active", "Deal Size": 1000000}
    ]
  },
  "meta": {
    "pagination": {"rows": {"nextCursor": "...", "prevCursor": null}}
  }
}
```

**Key differences from `query` output:**
- Data key is `rows` (not an entity-type-named array)
- Each row includes `listEntryId`, `entityType`, `entityId`, `entityName` as base fields
- Custom field values are keyed by **field name** (not field ID)
- Pagination is under `meta.pagination.rows`

## Performance

### Expand InteractionDates

- **Parallel fetching**: Entity fetches and person name resolution run in parallel
- **Shared concurrency limits**: Person API calls bounded to prevent rate limiting
- **Graceful degradation**: If person name lookup fails, falls back to "Person {id}"
- **Progress reporting**: Shows per-record progress for large expansions

For large datasets (500+ records), expect ~2 seconds per record.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XAFFINITY_QUERY_CONCURRENCY` | 15 | Max concurrent API calls for fetches/expansions |
