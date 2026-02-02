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

# Check if API key is configured
check_result=$(xaffinity --json config check-key 2>/dev/null || echo '{"data":{"configured":false}}')
configured=$(echo "$check_result" | jq -r '.data.configured // false')

if [ "$configured" = "true" ]; then
  exit 0  # Key configured, allow command
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
