# Claude Code Plugins & Skills

Two [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugins provide **skills** that teach Claude best practices for the Affinity SDK and CLI:

| Plugin | Best For | Key Feature |
|--------|----------|-------------|
| **sdk** | Python developers | Type-safe SDK patterns |
| **cli** | CLI power users | CLI skill + API key guard hook |

All plugins are installed from the `xaffinity` marketplace.

!!! info "What are skills?"
    Skills are knowledge packages that Claude loads when relevant. They teach Claude domain-specific patterns, best practices, and gotchas—so you don't have to explain them in every prompt.

!!! tip "Looking for MCP?"
    For agentic workflows (meeting prep, pipeline management, warm intros), see the [MCP Server](../mcp/index.md) documentation. The MCP server works with any MCP client, not just Claude.

## Installation

Add the marketplace (one-time):

```bash
/plugin marketplace add yaniv-golan/affinity-sdk
```

Install the plugin(s) you need:

```bash
# For Python SDK development
/plugin install sdk@xaffinity

# For CLI usage + hooks
/plugin install cli@xaffinity
```

You can install both plugins. They complement each other.

---

## SDK Plugin (affinity-python-sdk skill)

Teaches Claude the correct patterns for writing Python scripts with the Affinity SDK.

### What the skill teaches Claude

**Use typed IDs (not raw integers)**

```python
from affinity.types import PersonId, CompanyId

client.persons.get(PersonId(123))     # Correct
client.persons.get(123)               # Wrong - type error
```

**Use context managers**

```python
with Affinity.from_env() as client:   # Correct
    ...

client = Affinity.from_env()          # May leak resources
```

**Use read-only mode by default**

```python
from affinity.policies import Policies, WritePolicy

# Default: read-only (prevents accidental data modification)
with Affinity.from_env(policies=Policies(write=WritePolicy.DENY)) as client:
    ...
```

**Filters only work on custom fields**

```python
from affinity import F

# Works - custom fields
client.persons.list(filter=F.field("Department").equals("Sales"))

# Won't work - built-in properties like firstName, lastName, domain, etc.
```

### Example prompts

- "Write a script to export all companies to CSV"
- "How do I filter persons by a custom field?"
- "Get all entries from my Deal Pipeline list"

---

## CLI Plugin (xaffinity-cli-usage skill)

Teaches Claude the correct patterns for running `xaffinity` CLI commands.

### What the skill teaches Claude

- Always use `--readonly` by default
- Use `--json` for structured, parseable output
- Run `xaffinity config check-key --json` to verify API key configuration
- Use `--all` with caution (can be slow for large datasets)
- Filters only work on custom fields

### Example prompts

- "Export all my contacts to CSV"
- "Find the company with domain acme.com"
- "Show me all entries in my Deal Pipeline"

---

## MCP Server

For agentic workflows like meeting preparation, interaction logging, and pipeline management, use the MCP server.

The MCP server is protocol-agnostic and works with any MCP client (Claude Desktop, Cursor, Windsurf, VS Code + Copilot, ChatGPT Desktop, and others).

**Install via Claude Code:**

```bash
/plugin install mcp@xaffinity
```

**Full documentation:** [MCP Server](../mcp/index.md)

---

## Managing Plugins

### Updating

```bash
/plugin marketplace update
/plugin update sdk@xaffinity
/plugin update cli@xaffinity
```

### Uninstalling

```bash
/plugin uninstall sdk@xaffinity
/plugin uninstall cli@xaffinity
```
