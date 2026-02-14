# Include & Expand Reference

## Include Relationships

Fetch related entities in a single query. Results appear in a separate `included` section.

```json
{
  "from": "persons",
  "include": ["companies", "opportunities"],
  "limit": 50
}
```

### Available Relationships

| From | Can Include |
|------|-------------|
| `persons` | `companies`, `opportunities`, `interactions`, `notes`, `listEntries` |
| `companies` | `persons`, `opportunities`, `interactions`, `notes`, `listEntries` |
| `opportunities` | `persons`, `companies`, `interactions` |
| `lists` | `entries` |
| `listEntries` | `entity`, `persons`, `companies`, `opportunities`, `interactions` |

**Note:** For `listEntries`:
- `entity` dynamically resolves to person/company/opportunity based on entityType
- `persons`, `companies`, `opportunities`, `interactions` fetch related entities for each list entry

### Include Output Format

Included data appears in a separate `included` section keyed by relationship name:

```json
{
  "data": [{"id": 123, "firstName": "John", "organizationIds": [456]}],
  "included": {
    "companies": [{"id": 456, "name": "Acme Inc", "domain": "acme.com"}]
  }
}
```

In **markdown** format, included data appears as separate tables with headers like "Included: companies".

Parent records reference included entities via ID fields (e.g., `organizationIds` for companies). The `included` section contains deduplicated records.

### Parameterized Includes for listEntries

When including `interactions` for listEntries, you can customize the fetch with parameters:

```json
{
  "from": "listEntries",
  "where": {"path": "listName", "op": "eq", "value": "Dealflow"},
  "include": [
    {"interactions": {"limit": 50, "days": 180}},
    {"opportunities": {"list": "Pipeline"}}
  ]
}
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `limit` | Max interactions per entity | 100 |
| `days` | Lookback window in days | 90 |
| `list` | Scope opportunities to specific list name/ID | All |
| `where` | Filter included entities | None |

## Expand Computed Data

Unlike `include` (which fetches related entities), `expand` adds computed data directly to each record.

```json
{
  "from": "listEntries",
  "where": {"path": "listName", "op": "eq", "value": "Dealflow"},
  "expand": ["interactionDates", "unreplied"],
  "limit": 50
}
```

### Available Expansions

| Expansion | Supported Entities | Description |
|-----------|-------------------|-------------|
| `interactionDates` | `persons`, `companies`, `listEntries` | Last/next meeting dates, email dates, team members |
| `unreplied` | `persons`, `companies`, `opportunities`, `listEntries` | Detect unreplied incoming messages (date, daysSince, type, subject) |

### Interaction Dates Output

```json
{
  "id": 123,
  "name": "Acme Corp",
  "interactionDates": {
    "lastMeeting": {
      "date": "2026-01-08T10:00:00Z",
      "daysSince": 5,
      "teamMembers": ["Bob Smith", "Carol Jones"]
    },
    "nextMeeting": {
      "date": "2026-01-20T14:00:00Z",
      "daysUntil": 7,
      "teamMembers": ["Alice Wong"]
    },
    "lastEmail": {
      "date": "2026-01-10T09:30:00Z",
      "daysSince": 3
    },
    "lastInteraction": {
      "date": "2026-01-10T09:30:00Z",
      "daysSince": 3
    }
  }
}
```

### Include vs Expand

| Feature | `include` | `expand` |
|---------|-----------|----------|
| Purpose | Fetch related entities | Add computed data to records |
| Output | Separate `included` section | Merged into each record |
| Example | `include: ["companies"]` -> company records | `expand: ["interactionDates"]` -> dates on each record |

Both cause N+1 API calls. Always `dryRun: true` first.
