#!/bin/bash
set -euo pipefail

input=$(cat)
# Handle both object and string formats for tool_input
# Object: {"tool_input": {"command": "..."}}
# String: {"tool_input": "..."}
command=$(echo "$input" | jq -r '
  if .tool_input | type == "object" then
    .tool_input.command // ""
  elif .tool_input | type == "string" then
    .tool_input
  else
    ""
  end
' 2>/dev/null || echo "")

# Not an xaffinity command - allow
if [[ "$command" != *"xaffinity"* ]]; then
  exit 0
fi

# Config/help commands are always allowed
if [[ "$command" =~ xaffinity[[:space:]]*(--help|--version) ]] || \
   [[ "$command" =~ xaffinity[[:space:]]+config ]] || \
   [[ "$command" =~ --help ]]; then
  exit 0
fi

# Check 1: env var (fast path — no subprocess)
if [ -n "${AFFINITY_API_KEY:-}" ]; then
  exit 0
fi

# Check 2: xaffinity check-key WITH --dotenv (covers .env file)
# Note: --dotenv hard-fails if .env doesn't exist, so we fall through on failure
if xaffinity --dotenv --json config check-key 2>/dev/null | jq -e '.data.configured == true' >/dev/null 2>&1; then
  exit 0
fi

# Check 3: xaffinity check-key WITHOUT --dotenv (covers config.toml)
if xaffinity --json config check-key 2>/dev/null | jq -e '.data.configured == true' >/dev/null 2>&1; then
  exit 0
fi

# Not configured - block with guidance
cat >&2 << 'EOF'
{
  "hookSpecificOutput": {
    "permissionDecision": "deny"
  },
  "systemMessage": "BLOCKED: Affinity API key not configured. Tell the user to run 'xaffinity config setup-key' to configure (interactive - user must run it themselves). Then retry."
}
EOF
exit 2
