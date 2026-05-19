"""
MCP Server that wraps xaffinity CLI via CLI Gateway pattern.

7 tools expose the CLI:
- discover-commands: search available commands
- execute-read-command: run any read command
- execute-write-command: run any write command
- query: structured queries
- get-entity-dossier: comprehensive entity info
- get-file-url: presigned file download URL
- read-xaffinity-resource: static/dynamic resources

Security policies:
- AFFINITY_MCP_READ_ONLY=1: blocks write commands
- AFFINITY_MCP_DISABLE_DESTRUCTIVE=1: blocks delete commands
- --all flag blocked to prevent unbounded scans
- Default limits injected for pagination
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Environment-based security policies
READ_ONLY_MODE = os.environ.get("AFFINITY_MCP_READ_ONLY") == "1"
DISABLE_DESTRUCTIVE = os.environ.get("AFFINITY_MCP_DISABLE_DESTRUCTIVE") == "1"

# Pagination safety limits
DEFAULT_LIMIT = 1000
MAX_LIMIT = 10000

# Blocked flags that could cause unbounded scans
BLOCKED_FLAGS = {"--all", "-a", "--no-limit"}

# Cache for command registry
_command_cache: dict[str, Any] | None = None

# Static resources
_INTERACTION_ENUMS = {
    "interactionTypes": [
        {"value": "call", "label": "Phone Call", "description": "Voice call"},
        {"value": "meeting", "label": "Meeting", "description": "Scheduled meeting"},
        {"value": "email", "label": "Email", "description": "Email correspondence"},
        {
            "value": "chat-message",
            "label": "Chat Message",
            "description": "Instant message",
            "aliases": ["chat"],
        },
    ],
    "interactionDirections": [
        {"value": "incoming", "label": "Incoming", "description": "Received from contact"},
        {"value": "outgoing", "label": "Outgoing", "description": "Sent to contact"},
    ],
}

_DATA_MODEL_SUMMARY = """# Affinity Data Model

## Core Concepts

### Companies and Persons (Global Entities)
Exist globally in CRM, independent of any list.
- Commands: `company ls`, `person ls`, `company get`, `person get`

### Opportunities (List-Scoped)
ONLY exist within a specific list (pipeline).
- Commands: `opportunity ls`, `opportunity get`

### Lists (Collections with Custom Fields)
Pipelines/collections with custom Fields.
- Commands: `list ls`, `list get`, `list export`

### List Entries (Entity + List Membership)
Entity added to a list becomes List Entry with field values.
- Commands: `list export`, `list-entry get`

## Selectors: Names Work Directly
```
list export Dealflow --filter "Status=New"
company get "Acme Corp"
person get john@example.com
```

## Common Patterns
- `list export Dealflow --filter 'Status="New"'` - filtered entries
- `company get 12345 --expand list-entries` - list membership
- `interaction ls --type all --company-id 12345` - interactions
- `field ls --list-id Dealflow` - list fields

## Filter Syntax
`--filter 'field op "value"'` where op is = != =~ (contains) =^ (starts) =$ (ends) > < >= <=
"""


def _find_cli() -> str:
    """Find xaffinity CLI."""
    cli = shutil.which("xaffinity")
    if cli:
        return cli
    raise RuntimeError("xaffinity CLI not found. Install: pip install affinity-sdk[cli]")


def _run_cli(args: list[str], timeout: int = 120, input_data: str | None = None) -> dict[str, Any]:
    """Run xaffinity CLI command and return parsed JSON."""
    cli = _find_cli()
    cmd = [cli] + args

    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "timeout", "message": f"Timed out after {timeout}s"}}

    try:
        if result.stdout:
            return json.loads(result.stdout)
        return {"ok": False, "error": {"type": "empty", "message": result.stderr or "No output"}}
    except json.JSONDecodeError:
        return {"ok": result.returncode == 0, "output": result.stdout, "stderr": result.stderr}


def _get_all_commands() -> list[dict[str, Any]]:
    """Get all CLI commands from help JSON."""
    global _command_cache
    if _command_cache is not None:
        return _command_cache.get("commands", [])

    # All command groups including missing ones from review
    groups = [
        "company",
        "person",
        "list",
        "list-entry",
        "opportunity",
        "note",
        "reminder",
        "webhook",
        "interaction",
        "field",
        "task",
        "relationship-strength",
        "file-url",
        "config",
        "whoami",
    ]

    all_commands: list[dict[str, Any]] = []
    cli = _find_cli()

    for group in groups:
        try:
            result = subprocess.run(
                [cli, group, "--help", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                if "commands" in data:
                    all_commands.extend(data["commands"])
        except Exception:
            continue

    # Dedupe by command name. Some commands surface under multiple parent
    # groups in `xaffinity <group> --help --json` (e.g. `list-entry`
    # subcommands also appear inside the `list` group's help, and some
    # subcommands like `interaction ls` show up 5+ times). Without
    # dedup, discover-commands repeats them in its output.
    seen: set[str] = set()
    unique_commands: list[dict[str, Any]] = []
    for cmd in all_commands:
        name = cmd.get("name")
        if isinstance(name, str) and name not in seen:
            seen.add(name)
            unique_commands.append(cmd)

    _command_cache = {"commands": unique_commands}
    return unique_commands


def _get_command_info(command_name: str) -> dict[str, Any] | None:
    """Get command info by name."""
    for cmd in _get_all_commands():
        if cmd.get("name") == command_name:
            return cmd
    return None


def _search_commands(query: str, category: str = "all", limit: int = 10) -> list[dict[str, Any]]:
    """Search commands by keyword with scoring."""
    commands = _get_all_commands()
    query_lower = query.lower()
    query_tokens = query_lower.split()

    scored_results: list[tuple[int, dict[str, Any]]] = []

    for cmd in commands:
        cmd_category = cmd.get("category", "read")

        # Filter by category (read-only mode forces read)
        if READ_ONLY_MODE and cmd_category == "write":
            continue
        if category != "all" and cmd_category != category:
            continue

        name = cmd.get("name", "").lower()
        desc = cmd.get("description", "").lower()

        score = 0
        # Exact name match
        if query_lower == name:
            score += 1000
        # Name prefix match
        elif name.startswith(query_lower):
            score += 500
        # Token matches in name
        for token in query_tokens:
            if token in name:
                score += 100
            if token in desc:
                score += 10

        if score > 0:
            scored_results.append((score, cmd))

    # Sort by score descending
    scored_results.sort(key=lambda x: -x[0])
    return [cmd for _, cmd in scored_results[:limit]]


def _format_commands_text(commands: list[dict[str, Any]], detail: str = "summary") -> str:
    """Format commands as compact text."""
    if not commands:
        return "No matching commands found."

    lines = []
    if detail == "list":
        lines.append("# Commands")
        for cmd in commands:
            lines.append(f"- {cmd['name']}")
    elif detail == "summary":
        lines.append("# cmd | category | description")
        for cmd in commands:
            cat = cmd.get("category", "?")[0]
            desc = cmd.get("description", "")[:60]
            destructive = " [DESTRUCTIVE]" if cmd.get("destructive") else ""
            lines.append(f"{cmd['name']} | {cat} | {desc}{destructive}")
    else:  # full
        for cmd in commands:
            lines.append(f"## {cmd['name']}")
            lines.append(f"Category: {cmd.get('category', 'unknown')}")
            lines.append(f"Description: {cmd.get('description', '')}")
            if cmd.get("destructive"):
                lines.append("⚠️ DESTRUCTIVE - requires confirm=true")
            params = cmd.get("parameters", {})
            if params:
                lines.append("Parameters:")
                for p, info in params.items():
                    req = " (required)" if info.get("required") else ""
                    lines.append(f"  {p}: {info.get('type', '?')}{req} - {info.get('help', '')}")
            pos = cmd.get("positionals", [])
            if pos:
                lines.append("Positional args:")
                for p in pos:
                    req = " (required)" if p.get("required") else ""
                    lines.append(f"  {p['name']}: {p.get('type', '?')}{req}")
            lines.append("")

    return "\n".join(lines)


def _validate_argv(argv: list[str]) -> tuple[bool, str]:
    """Validate argv for blocked flags. Returns (valid, error_message)."""
    for arg in argv:
        if arg in BLOCKED_FLAGS:
            return (
                False,
                f"Flag '{arg}' is blocked via MCP to prevent unbounded scans. Use --max-results instead.",
            )
        if arg == "--csv":
            # The MCP wrapper auto-appends --json so it can parse the
            # result; the CLI then errors out with "--json and --csv are
            # mutually exclusive". Reject up front with a useful hint
            # instead of letting that confusing CLI message reach the
            # caller (observed agents misreading it as "I should drop
            # --json" when they never passed --json — the wrapper did).
            return (
                False,
                (
                    "Flag '--csv' is not supported via MCP — the wrapper "
                    "requires JSON output for parsing. For large result "
                    "sets, use --max-results with --cursor pagination."
                ),
            )
    return True, ""


# Filter targets that the Affinity V2 API silently drops. Confirmed
# empirically against /companies (all three of `name =`, `name =~`, and
# `domain =` returned the unfiltered list head with no error or warning).
# Per docs/public/cli/commands.md: "--filter only works with custom
# fields. To filter on built-in properties like name, domain, etc.,
# use --json output with jq." Surface this loudly instead of letting
# silent drops masquerade as "no matches" or "wrong filter syntax".
_BUILTIN_FILTER_FIELDS = frozenset(
    {
        "name",
        "domain",
        "domains",
        "id",
        "firstName",
        "lastName",
        "email",
        "emails",
    }
)


# A bare identifier at the start of the filter expression. Matches the
# `_read_unquoted('=!&|()"')` behavior in the CLI's filter tokenizer
# (affinity/filters.py): an unquoted field name ends at any whitespace
# or any operator-introducing character. So we accept both `name = "X"`
# (whitespace-separated) and `name="X"` (operator-adjacent) — both are
# valid filter syntax and both must trigger the preflight.
_FILTER_FIELD_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)")


def _builtin_filter_violation(argv: list[str]) -> str | None:
    """Return the offending built-in field name if argv contains a --filter
    expression targeting one (e.g. `--filter 'name = "Acme"'` or
    `--filter 'name="Acme"'`), else None.
    """
    for i, a in enumerate(argv):
        if a == "--filter" and i + 1 < len(argv):
            m = _FILTER_FIELD_RE.match(argv[i + 1])
            if m and m.group(1) in _BUILTIN_FILTER_FIELDS:
                return m.group(1)
    return None


def _inject_default_limit(argv: list[str]) -> list[str]:
    """Inject default --max-results if not present."""
    has_limit = any(a in argv for a in ["--max-results", "--limit", "-n"])
    if not has_limit:
        return argv + ["--max-results", str(DEFAULT_LIMIT)]
    return argv


def _make_error(error_type: str, message: str) -> dict[str, Any]:
    """Create error response."""
    return {"ok": False, "error": {"type": error_type, "message": message}}


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="discover-commands",
        description="Search CLI commands by keyword. Use this first to find the right command.\n\nExamples: 'find companies', 'create person', 'export list', 'log meeting'",
        inputSchema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "What you want to do"},
                "category": {
                    "type": "string",
                    "enum": ["read", "write", "all"],
                    "default": "all",
                    "description": "Filter: 'read', 'write', 'all'",
                },
                "detail": {
                    "type": "string",
                    "enum": ["list", "summary", "full"],
                    "default": "summary",
                    "description": "Detail level",
                },
                "limit": {"type": "integer", "default": 10, "description": "Max results"},
            },
        },
    ),
    Tool(
        name="execute-read-command",
        description="Execute a read-only CLI command. Use discover-commands first.\n\n--json added automatically. --all flag blocked (use --max-results).\n\nNOTE: --filter is only honored on CUSTOM fields. The Affinity V2 API silently drops --filter on built-in fields (name, domain, domains, id, firstName, lastName, email, emails) and returns the unfiltered list. This MCP server refuses such filters with error.type='unsupported_filter'. To resolve an entity by built-in identifier, use 'company get name:<value>' or 'person get email:<value>'; on ambiguity the response includes error.details.matches with candidate IDs. For free-text search use '--query <text>'.\n\nExamples:\n- command='person get', argv=['email:john@example.com']\n- command='company get', argv=['name:Acme']\n- command='company ls', argv=['--filter', 'Industry = \"Software\"', '--max-results', '50']  # custom field, works\n- command='company ls', argv=['--query', 'Acme', '--max-results', '20']  # free-text search across built-ins",
        inputSchema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "description": "CLI command (e.g., 'person get')"},
                "argv": {"type": "array", "items": {"type": "string"}, "description": "Arguments"},
                "timeout": {"type": "integer", "default": 120, "description": "Timeout seconds"},
            },
        },
    ),
    Tool(
        name="execute-write-command",
        description="Execute a write CLI command. Use discover-commands first.\n\nFor destructive commands (delete), set confirm=true.\n\nExamples:\n- command='person create', argv=['--first-name', 'John']\n- command='company delete', argv=['456'], confirm=true",
        inputSchema={
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {"type": "string", "description": "CLI command"},
                "argv": {"type": "array", "items": {"type": "string"}, "description": "Arguments"},
                "confirm": {
                    "type": "boolean",
                    "default": False,
                    "description": "Required for delete commands",
                },
                "timeout": {"type": "integer", "default": 60, "description": "Timeout seconds"},
            },
        },
    ),
    Tool(
        name="query",
        description='Execute structured query. Supports filtering, includes, aggregates.\n\nEntities: persons, companies, opportunities, listEntries, interactions, notes\n\nExamples:\n- {"from": "persons", "where": {"path": "email", "op": "contains", "value": "@acme.com"}, "limit": 50}',
        inputSchema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "object",
                    "required": ["from"],
                    "properties": {
                        "from": {
                            "type": "string",
                            "enum": [
                                "persons",
                                "companies",
                                "opportunities",
                                "listEntries",
                                "interactions",
                                "notes",
                            ],
                        },
                        "where": {"type": "object"},
                        "select": {"type": "array", "items": {"type": "string"}},
                        "include": {"type": "array", "items": {"type": "string"}},
                        "orderBy": {"type": "array"},
                        "groupBy": {"type": "string"},
                        "aggregate": {"type": "object"},
                        "limit": {"type": "integer"},
                    },
                },
                "dry_run": {"type": "boolean", "default": False},
                "format": {
                    "type": "string",
                    "enum": ["json", "toon", "markdown", "csv", "jsonl"],
                    "default": "json",
                },
                "max_records": {
                    "type": "integer",
                    "default": 1000,
                    "description": "Max records (default 1000, max 10000)",
                },
            },
        },
    ),
    Tool(
        name="get-entity-dossier",
        description="Get comprehensive dossier for person/company/opportunity. Aggregates: details, relationship strength, interactions, notes, list memberships.",
        inputSchema={
            "type": "object",
            "required": ["entityType", "entityId"],
            "properties": {
                "entityType": {"type": "string", "enum": ["person", "company", "opportunity"]},
                "entityId": {"type": "integer"},
                "includeInteractions": {"type": "boolean", "default": True},
                "includeNotes": {"type": "boolean", "default": True},
                "includeLists": {"type": "boolean", "default": True},
            },
        },
    ),
    Tool(
        name="get-file-url",
        description="Get presigned URL to download a file. Valid 60 seconds. Get file IDs from 'company files ls' etc.",
        inputSchema={
            "type": "object",
            "required": ["fileId"],
            "properties": {
                "fileId": {"type": "integer", "description": "File ID"},
            },
        },
    ),
    Tool(
        name="read-xaffinity-resource",
        description="Read xaffinity:// resource.\n\nAvailable:\n- xaffinity://data-model\n- xaffinity://me\n- xaffinity://interaction-enums\n- xaffinity://field-catalogs/{listId}\n- xaffinity://saved-views/{listId}",
        inputSchema={
            "type": "object",
            "required": ["uri"],
            "properties": {
                "uri": {"type": "string", "description": "Resource URI"},
            },
        },
    ),
]


async def serve() -> None:
    """Run the MCP server."""
    server = Server("affinity")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        # In read-only mode, don't expose execute-write-command
        if READ_ONLY_MODE:
            return [t for t in TOOLS if t.name != "execute-write-command"]
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "discover-commands":
                query = arguments["query"]
                category = arguments.get("category", "all")
                # Force read category in read-only mode
                if READ_ONLY_MODE and category in ("write", "all"):
                    category = "read"
                detail = arguments.get("detail", "summary")
                limit = arguments.get("limit", 10)

                commands = _search_commands(query, category, limit)
                output = _format_commands_text(commands, detail)
                return [TextContent(type="text", text=output)]

            elif name == "execute-read-command":
                command = arguments["command"]
                argv = arguments.get("argv", [])
                timeout = arguments.get("timeout", 120)

                # Validate command is read category
                cmd_info = _get_command_info(command)
                if cmd_info and cmd_info.get("category") == "write":
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                _make_error(
                                    "category_mismatch",
                                    f"'{command}' is a write command. Use execute-write-command.",
                                )
                            ),
                        )
                    ]

                # Validate argv
                valid, err = _validate_argv(argv)
                if not valid:
                    return [
                        TextContent(type="text", text=json.dumps(_make_error("blocked_flag", err)))
                    ]

                # Preflight: Affinity V2 silently drops --filter on built-in
                # identifiers. Refuse loudly with a recovery hint instead of
                # letting the call return an unfiltered list disguised as a
                # filtered one.
                violating_field = _builtin_filter_violation(argv)
                if violating_field:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                _make_error(
                                    "unsupported_filter",
                                    f"--filter on built-in field '{violating_field}' is not supported by the "
                                    f"Affinity V2 API; the request would silently return the unfiltered list. "
                                    f"To resolve an entity by built-in identifier, call execute-read-command "
                                    f"with command='company get' (or 'person get') and argv=['name:<value>'] "
                                    f"or argv=['email:<value>'] — on ambiguity the response contains "
                                    f"error.type='ambiguous_resolution' with error.details.matches listing "
                                    f"candidate IDs. For free-text search use --query '<text>' instead of "
                                    f"--filter. --filter is only supported on custom fields (e.g. "
                                    f"'Industry = \"Software\"').",
                                )
                            ),
                        )
                    ]

                # Inject default limit
                argv = _inject_default_limit(argv)

                cmd_parts = command.split()
                full_args = cmd_parts + argv + ["--json"]

                result = _run_cli(full_args, timeout=timeout)
                result["_executed"] = ["xaffinity"] + full_args
                return [
                    TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
                ]

            elif name == "execute-write-command":
                # Block in read-only mode
                if READ_ONLY_MODE:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                _make_error(
                                    "read_only_mode",
                                    "Write commands blocked. AFFINITY_MCP_READ_ONLY=1",
                                )
                            ),
                        )
                    ]

                command = arguments["command"]
                argv = arguments.get("argv", [])
                confirm = arguments.get("confirm", False)
                timeout = arguments.get("timeout", 60)

                # Validate command is write category
                cmd_info = _get_command_info(command)
                if cmd_info:
                    if cmd_info.get("category") == "read":
                        return [
                            TextContent(
                                type="text",
                                text=json.dumps(
                                    _make_error(
                                        "category_mismatch",
                                        f"'{command}' is a read command. Use execute-read-command.",
                                    )
                                ),
                            )
                        ]

                    # Check destructive policy
                    if cmd_info.get("destructive"):
                        if DISABLE_DESTRUCTIVE:
                            return [
                                TextContent(
                                    type="text",
                                    text=json.dumps(
                                        _make_error(
                                            "destructive_disabled",
                                            f"Destructive commands blocked. AFFINITY_MCP_DISABLE_DESTRUCTIVE=1",
                                        )
                                    ),
                                )
                            ]
                        if not confirm:
                            return [
                                TextContent(
                                    type="text",
                                    text=json.dumps(
                                        _make_error(
                                            "confirmation_required",
                                            f"'{command}' is destructive. Set confirm=true to proceed.",
                                        )
                                    ),
                                )
                            ]

                # Validate argv
                valid, err = _validate_argv(argv)
                if not valid:
                    return [
                        TextContent(type="text", text=json.dumps(_make_error("blocked_flag", err)))
                    ]

                # Same V2 filter-on-built-in guard as execute-read-command.
                violating_field = _builtin_filter_violation(argv)
                if violating_field:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                _make_error(
                                    "unsupported_filter",
                                    f"--filter on built-in field '{violating_field}' is not supported by the "
                                    f"Affinity V2 API and would silently target the unfiltered set. "
                                    f"Resolve the target entity first via 'company get name:<value>' / "
                                    f"'person get email:<value>', then operate on the returned ID.",
                                )
                            ),
                        )
                    ]

                cmd_parts = command.split()
                full_args = cmd_parts + argv

                if confirm:
                    full_args.append("--yes")
                full_args.append("--json")

                result = _run_cli(full_args, timeout=timeout)
                result["_executed"] = ["xaffinity"] + full_args
                return [
                    TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
                ]

            elif name == "query":
                query_obj = arguments["query"]
                dry_run = arguments.get("dry_run", False)
                fmt = arguments.get("format", "json")
                max_records = min(arguments.get("max_records", DEFAULT_LIMIT), MAX_LIMIT)

                # Write query to a temp file and pass via --file. The CLI's
                # query subcommand does not expose --stdin; the bash MCP
                # wrapper at mcp/tools/query/tool.sh switched to --file in
                # commit dada1ad after stdin pipeline issues in VM
                # environments. This Python server was missed by that fix
                # and every call previously failed with
                # `usage_error: "No such option '--stdin'"`.
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".json",
                    prefix="xaff-query-",
                    delete=False,
                    encoding="utf-8",
                ) as tf:
                    tf.write(json.dumps(query_obj))
                    query_path = tf.name
                try:
                    args = [
                        "query",
                        "--file",
                        query_path,
                        "--output",
                        fmt,
                        "--max-records",
                        str(max_records),
                    ]
                    if dry_run:
                        args.append("--dry-run")
                    result = _run_cli(args, timeout=300)
                finally:
                    try:
                        os.unlink(query_path)
                    except OSError:
                        pass
                return [
                    TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))
                ]

            elif name == "get-entity-dossier":
                entity_type = arguments["entityType"]
                entity_id = arguments["entityId"]
                include_interactions = arguments.get("includeInteractions", True)
                include_notes = arguments.get("includeNotes", True)
                include_lists = arguments.get("includeLists", True)

                dossier: dict[str, Any] = {
                    "entity": {"type": entity_type, "id": entity_id},
                    "details": {},
                    "relationshipStrength": None,
                    "recentInteractions": [],
                    "recentNotes": [],
                    "listMemberships": [],
                }

                entity_result = _run_cli([entity_type, "get", str(entity_id), "--json"])
                if entity_result.get("ok") and "data" in entity_result:
                    dossier["details"] = entity_result["data"].get(entity_type, {})

                if entity_type == "person":
                    rs_result = _run_cli(
                        ["relationship-strength", "ls", "--external-id", str(entity_id), "--json"]
                    )
                    if rs_result.get("ok") and "data" in rs_result:
                        strengths = rs_result["data"].get("relationshipStrengths", [])
                        if strengths:
                            dossier["relationshipStrength"] = strengths[0]

                if include_interactions:
                    int_result = _run_cli(
                        [
                            "interaction",
                            "ls",
                            f"--{entity_type}-id",
                            str(entity_id),
                            "--type",
                            "all",
                            "--days",
                            "365",
                            "--max-results",
                            "10",
                            "--json",
                        ]
                    )
                    if int_result.get("ok") and "data" in int_result:
                        dossier["recentInteractions"] = int_result["data"]

                if include_notes:
                    notes_result = _run_cli(
                        [
                            "note",
                            "ls",
                            f"--{entity_type}-id",
                            str(entity_id),
                            "--max-results",
                            "10",
                            "--json",
                        ]
                    )
                    if notes_result.get("ok") and "data" in notes_result:
                        dossier["recentNotes"] = notes_result["data"]

                if include_lists:
                    lists_result = _run_cli(
                        ["list-entry", "ls", f"--{entity_type}-id", str(entity_id), "--json"]
                    )
                    if lists_result.get("ok") and "data" in lists_result:
                        dossier["listMemberships"] = lists_result["data"].get("entries", [])

                return [
                    TextContent(type="text", text=json.dumps(dossier, indent=2, ensure_ascii=False))
                ]

            elif name == "get-file-url":
                file_id = arguments["fileId"]
                result = _run_cli(["file-url", str(file_id), "--json"])
                if result.get("ok") and "data" in result:
                    return [TextContent(type="text", text=json.dumps(result["data"], indent=2))]
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "read-xaffinity-resource":
                uri = arguments["uri"]
                if not uri.startswith("xaffinity://"):
                    return [
                        TextContent(type="text", text=json.dumps({"error": "Invalid URI format"}))
                    ]

                path = uri[len("xaffinity://") :]
                parts = path.split("/", 1)
                resource_name = parts[0]
                resource_param = parts[1] if len(parts) > 1 else None

                if resource_name == "data-model":
                    return [TextContent(type="text", text=_DATA_MODEL_SUMMARY)]
                elif resource_name == "interaction-enums":
                    return [TextContent(type="text", text=json.dumps(_INTERACTION_ENUMS, indent=2))]
                elif resource_name == "me":
                    result = _run_cli(["whoami", "--json"])
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif resource_name == "me-person-id":
                    result = _run_cli(["whoami", "--json"])
                    if result.get("ok") and "data" in result:
                        person_id = result["data"].get("user", {}).get("personId")
                        return [TextContent(type="text", text=json.dumps({"personId": person_id}))]
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif resource_name == "field-catalogs" and resource_param:
                    result = _run_cli(["field", "ls", "--list-id", resource_param, "--json"])
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                elif resource_name == "saved-views" and resource_param:
                    result = _run_cli(["list", "get", resource_param, "--json"])
                    if result.get("ok") and "data" in result:
                        views = result["data"].get("list", {}).get("savedViews", [])
                        return [
                            TextContent(
                                type="text", text=json.dumps({"savedViews": views}, indent=2)
                            )
                        ]
                    return [TextContent(type="text", text=json.dumps(result, indent=2))]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps({"error": f"Unknown resource: {resource_name}"}),
                        )
                    ]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"ok": False, "error": str(e)}))]

    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


def main() -> None:
    """Entry point for xaffinity-mcp command."""
    try:
        _find_cli()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(serve())


if __name__ == "__main__":
    main()
