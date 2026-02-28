---
name: xaffinity-cli-usage
description: >
  Runs xaffinity CLI commands to search, export, filter, and manage Affinity CRM data.
  Use when user asks to find people/companies/opportunities, export lists, query CRM data,
  get interactions, or mentions "xaffinity", "export to CSV", "Affinity CLI".
  Supports structured queries with aggregation/groupBy, saved-view server-side filtering,
  interaction history with date bounds, and CSV/JSON/TOON export.
---

# xaffinity CLI Usage

## REQUIRED FIRST STEP: Verify API Key

**STOP. Before doing ANYTHING else, run this command:**

```bash
xaffinity config check-key --json
```

This MUST be your first action when handling any Affinity request.

**If `"configured": true`** - Use the `pattern` field from the output for ALL subsequent commands:
- If `"pattern": "xaffinity --dotenv --readonly <command> --json"` -> use `--dotenv`
- If `"pattern": "xaffinity --readonly <command> --json"` -> no `--dotenv` needed

**If `"configured": false`** - Stop and help user set up:
1. Tell them: "You need to configure an Affinity API key first."
2. Direct them: Affinity -> Settings -> API -> Generate New Key
3. Tell them to run: `xaffinity config setup-key` (do NOT run it for them - it's interactive)

**Session cache:** Set up automatically at session start. If `AFFINITY_SESSION_CACHE` is not set, run: `export AFFINITY_SESSION_CACHE=$(xaffinity session start)` — this shares metadata across commands and avoids redundant API calls.

## IMPORTANT: Write Operations Require Explicit User Request

**Always use `--readonly` unless user explicitly requests writes.**

Write operations include creating, updating, or deleting:
- Notes, interactions, reminders
- List entries, field values
- Persons, companies, opportunities

## Destructive Commands Require Double Confirmation

**IMPORTANT**: Before executing ANY delete command, you MUST:

1. **Look up the entity first** to show the user what will be deleted
2. **Ask the user in your response** by showing them the entity details and requesting confirmation
3. **Wait for user's next message** - do NOT proceed until they explicitly confirm
4. **Only after user confirms** should you run the delete with `--yes`

Example flow:
```
User: "Delete person 123"
You: xaffinity --readonly person get 123 --json
You: "This will permanently delete John Smith (ID: 123, email: john@example.com).
      Type 'yes' to confirm deletion."
[Stop here and wait for user's response]

User: "yes"
You: xaffinity person delete 123 --yes
```

**Destructive commands**: `person delete`, `company delete`, `opportunity delete`, `note delete`, `reminder delete`, `field delete`, `list entry delete`, `interaction delete`

**Note**: This is conversation-based confirmation - you ask, then wait for the user's next message. The `--yes` flag bypasses the CLI's interactive prompt, but you must get explicit user confirmation in the conversation first.

## Critical Patterns

| Pattern | Purpose |
|---------|---------|
| `--readonly` | Prevent accidental data modification (ALWAYS use unless writing) |
| `--json` | Structured, parseable output (ALWAYS use for commands you will parse) |
| `--max-results N` | **Limit results (ALWAYS use on list/search commands)**. Aliases: `--limit`, `-n` |
| `--yes` | Skip confirmation on delete commands (use after user confirms) |
| `--help` | Discover command options (USE THIS, don't guess flags) |

**IMPORTANT: Always limit results.** Use `--max-results` on every `ls`, `list export`, `interaction ls`, and `note ls` command. Start small (10-50), increase only if needed. Unbounded queries can return hundreds of KB of data and make many API calls.

**Extract only what you need.** When you know which fields you need, pipe through `jq` instead of dumping the full JSON response. Skip this when exploring data for the first time.

```bash
# Get a person's ID for a follow-up command
xaffinity --readonly person get email:alice@example.com --json | jq -r '.data.person.id'

# Get just the fields you need to answer the user
xaffinity --readonly person get 123 --json | jq '.data.person | {id, firstName, lastName, primaryEmail}'

# Get entity names from a list export
xaffinity --readonly list export "Pipeline" --max-results 20 --json | jq '[.data.rows[] | {entityName, entityId}]'
```

## Multi-Source Tasks: Use a Script

When a task needs data from **2 or more** CLI commands (e.g., person details + interactions + list entries), write a **single bash script** instead of running commands one-by-one. Each separate command dumps its full JSON into the conversation — chaining 3-5 commands can waste hundreds of KB of context on raw data you only need a few facts from.

**Use a script when:** combining entity details with interactions, cross-referencing list entries with entities, generating summaries from multiple queries.

**A single command is fine when:** simple lookups (`person get email:...`), single writes (`note create`), quick searches (`person ls --query`).

### Bash + jq

Session caching is already active (set up at session start), so just use `jq` to extract the summary:

```bash
# Example: "Summarize my interactions with Acme in Q1"
CID=$(xaffinity --readonly company get domain:acme.com --json \
  | jq -r '.data.company.id')

xaffinity --readonly interaction ls --type all --company-id "$CID" \
  --after 2025-01-01T00:00:00Z --before 2025-03-31T23:59:59Z \
  --max-results 200 --json \
  | jq '{
    company: "Acme",
    total: (.data.interactions | length),
    by_type: (.data.interactions | group_by(.type)
              | map({type: .[0].type, count: length}))
  }'
```

This outputs ~200 bytes instead of ~100 KB of raw JSON.

### When to use Python instead

For complex joins across 3+ sources, conditional logic, pagination over large datasets, or when you need SDK features like `F` filters or `FieldResolver`, write a Python script using the Affinity SDK. The SDK skill has patterns for this.

## Selectors: Use Names, Not Just IDs

Most commands accept names, emails, or domains directly — no need to look up IDs first:

```bash
# These all work — no ID lookup needed:
xaffinity --readonly person get email:alice@example.com --json
xaffinity --readonly company get domain:acme.com --json
xaffinity --readonly list export "My Pipeline" --max-results 20 --json

# IDs also work:
xaffinity --readonly person get 12345 --json
```

## Common Commands

```bash
# Search entities (always limit results)
xaffinity --readonly person ls --query "John Smith" --max-results 10 --json
xaffinity --readonly company ls --query "Acme" --max-results 10 --json

# Get single entity by identifier
xaffinity --readonly person get email:alice@example.com --json
xaffinity --readonly company get domain:acme.com --json

# List entries from a named list
xaffinity --readonly list export "Pipeline" --max-results 20 --json

**JSON output key is `data.rows`** (not `data.listEntries` or `data.entries`). Each row contains `listEntryId`, `entityType`, `entityId`, `entityName`, plus field values keyed by field name.

# List all available lists
xaffinity --readonly list ls --json

# Export to CSV
xaffinity --readonly person ls --all --csv --csv-bom > contacts.csv
xaffinity --readonly list export "Pipeline" --all --csv --csv-bom > output.csv
```

## Interactions

Interactions require `--type` and exactly one entity ID (`--person-id`, `--company-id`, or `--opportunity-id`).

**Valid types:** `email`, `meeting`, `call`, `chat`, `chat-message`, `all`

**Date range:** Defaults to **all time** if not specified. Use `--days` or `--after`/`--before` to limit.

```bash
# Recent interactions (recommended: use --days and --max-results)
xaffinity --readonly interaction ls --type all --company-id 123 \
  --days 90 --max-results 50 --json

# Specific date range (max 1 year per API call; auto-chunked for larger ranges)
xaffinity --readonly interaction ls --type email --person-id 456 \
  --after 2025-01-01 --before 2025-12-31 --max-results 100 --json

# --days and --after are mutually exclusive
# Dates without timezone suffix are interpreted as local time; use Z for UTC:
#   --after 2025-01-01T00:00:00Z
```

**WARNING:** Without `--days` or `--after`, the CLI fetches ALL interactions since 2010. Multi-year ranges are auto-chunked into 365-day API calls. `--days 3650` = ~10 API calls per type. **Always use `--days` or `--max-results` to bound the query.**

### Creating Interactions

Interactions require **both internal AND external** person IDs:
- **Internal**: A workspace user (team member). Find yours with `xaffinity whoami`.
- **External**: A contact (non-team-member person in your CRM).

```bash
# Create a meeting — use --include-me to auto-add your person ID
xaffinity interaction create --type meeting \
  --person-id EXTERNAL_CONTACT_ID --include-me \
  --content "Discussed partnership" --date 2025-06-15T14:00:00Z --json

# Without --include-me, specify all person IDs explicitly
xaffinity interaction create --type email \
  --person-id YOUR_PERSON_ID --person-id CONTACT_ID \
  --content "Follow-up email" --date 2025-06-15T14:00:00Z --json
```

**Common error:** Forgetting to include an internal person ID causes a validation error. Use `--include-me` to avoid this.

## Expand/Include (N+1 Warning)

`--expand` on `list export` triggers **one additional API call per record**. Use `--max-results` to control cost.

```bash
# Safe: 20 records = ~21 API calls
xaffinity --readonly list export "Pipeline" --expand persons --max-results 20 --json

# Multiple expands compound the cost:
xaffinity --readonly list export "Pipeline" --expand persons --expand companies \
  --max-results 20 --json

# DANGEROUS: --expand with --all on a large list
# 500 entries = 501+ API calls, ~10 minutes
# xaffinity list export "Pipeline" --expand persons --all  # DON'T do this blindly
```

**Practical limits:** <=100 records is safe. 200 records ~5 min. 400+ records may hit timeouts.

## Query Command (Advanced)

Use `query` when you need capabilities beyond simple `ls` / `list export`:
- **Aggregation & groupBy** — summarize data (count, sum, avg by field)
- **Cross-entity filtering** — find persons based on their companies/interactions
- **Nested boolean logic** — complex AND/OR/NOT combinations
- **Dry-run mode** — preview API cost before executing
- **Include relationships** — fetch related entities in one query

### When to use query vs other commands

| Need | Use |
|------|-----|
| Simple search by name/email | `person ls --query` or `person get email:...` |
| Export list entries | `list export "ListName"` |
| Server-side filtered list | `list export --saved-view "ViewName"` |
| Aggregate/group data | `query` |
| Filter by related entities | `query` |
| Preview API cost first | `query --dry-run` |

### Basic patterns

```bash
# Always dry-run first for queries with include/expand/quantifiers
xaffinity --readonly query --dry-run --query '{"from": "listEntries", "where": {"path": "listName", "op": "eq", "value": "Dealflow"}, "groupBy": "fields.Status", "aggregate": {"count": {"count": true}}}' --json

# From a file (recommended for complex queries)
xaffinity --readonly query --file query.json --json

# Inline simple query
xaffinity --readonly query --query '{"from": "persons", "where": {"path": "email", "op": "contains", "value": "@acme.com"}, "limit": 20}' --json
```

### Query JSON structure

```json
{
  "from": "persons|companies|opportunities|listEntries|lists",
  "where": {"path": "field", "op": "eq", "value": "x"},
  "select": ["id", "firstName", "fields.Status"],
  "include": ["companies"],
  "expand": ["interactionDates"],
  "groupBy": "fields.Status",
  "aggregate": {"count": {"count": true}, "total": {"sum": "fields.Deal Size"}},
  "orderBy": [{"field": "name", "direction": "asc"}],
  "limit": 100
}
```

**Key rules:**
- `listEntries` queries MUST include a `where` filter on `listId` or `listName`
- `interactions` and `notes` can only be accessed via `include`, not queried directly
- `--dry-run` is REQUIRED before running queries with `include`, `expand`, or quantifiers (`all`, `none`, `exists`)
- Quantifiers (`all`, `none`, `exists`) cause N+1 API calls — always limit results

For full query reference (operators, aggregation, quantifiers, examples): see `references/query-guide.md`

## Filtering

### Entity commands (`person ls`, `company ls`): Filter works on ALL fields

```bash
# Core fields work:
xaffinity --readonly person ls --filter 'Email =~ "@acme.com"' --max-results 20 --json
xaffinity --readonly company ls --filter 'name =~ "Acme"' --max-results 20 --json

# Custom fields work:
xaffinity --readonly person ls --filter 'Department = "Sales"' --max-results 20 --json
```

### List export: `--filter` is CLIENT-SIDE (fetches everything first)

```bash
# SLOW on large lists — downloads ALL entries, then filters locally:
xaffinity --readonly list export "Pipeline" --filter 'Status = "Active"' --all --json

# FAST — use saved views for server-side filtering:
xaffinity --readonly list export "Pipeline" --saved-view "Active Deals" --max-results 50 --json
```

**For large lists (1000+ entries), prefer `--saved-view` over `--filter`.**

### Filter operators

```
=    exact match           'Status = "Active"'
!=   not equal             'Status != "Closed"'
=~   contains              'Email =~ "@acme"'
=^   starts with           'Name =^ "John"'
=$   ends with             'Domain =$ ".com"'
>    greater than           'Revenue > "1000000"'
<    less than
>=   greater or equal
<=   less or equal
&    AND                   'Status = "Active" & Region = "US"'
|    OR                    'Status = "New" | Status = "Pending"'
```

## Smart Fields ("Last Meeting", "Next Meeting")

These are UI-only and not in the API. Use `--with-interaction-dates` on **get** commands (not `ls`):

```bash
xaffinity --readonly person get email:alice@example.com --with-interaction-dates --json
xaffinity --readonly company get domain:acme.com --with-interaction-dates --json
```

## Gotchas & Workarounds

### Internal meetings NOT in interactions
The interactions API only shows meetings with **external** contacts.
```bash
# Workaround - use notes:
xaffinity --readonly note ls --person-id 123 --max-results 20 --json
# Then filter for isMeeting: true in the output
```

### --query and --filter are mutually exclusive
Use `--query` for fuzzy text search or `--filter` for structured filtering. Cannot combine both.

### Opportunities are bound to one list
Cannot search opportunities globally. Access them via `list export` on their specific list.

### Global organizations are read-only
Companies with `global: true` cannot be modified.

### Progress output goes to stderr
When piping JSON output through another program, progress messages appear on stderr (not stdout). JSON on stdout is clean. If you need to suppress progress: use `--quiet` or `-q`.

## Quick Reference

| Task | Command |
|------|---------|
| Find person by email | `person get email:user@example.com --json` |
| Find company by domain | `company get domain:acme.com --json` |
| Search people | `person ls --query "name" --max-results 10 --json` |
| Recent interactions | `interaction ls --type all --company-id ID --days 90 --max-results 50 --json` |
| Export list (bounded) | `list export "ListName" --max-results 100 --json` |
| Export list (full CSV) | `list export "ListName" --all --csv --csv-bom > out.csv` |
| List with server filter | `list export "ListName" --saved-view "ViewName" --max-results 50 --json` |
| Aggregate/group data | `query --dry-run --file query.json --json` (preview cost first) |
| Get command help | `xaffinity <command> --help` |

**Remember:** Prefix all commands with `xaffinity --readonly` (and `--dotenv` if `check-key` says so).

## Installation

```bash
pip install "affinity-sdk[cli]"
```

## Documentation

- Full CLI reference: `xaffinity --help`
- SDK docs: https://yaniv-golan.github.io/affinity-sdk/latest/
