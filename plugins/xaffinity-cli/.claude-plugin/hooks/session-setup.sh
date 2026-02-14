#!/usr/bin/env bash
set -euo pipefail

# Bootstrap xaffinity CLI for Cowork sessions.
# Safe in all environments: only acts when something is missing.
# - Claude Code (macOS): xaffinity already installed, key in config.toml/env — no-ops
# - Claude Desktop: not applicable (MCP server, not CLI)
# - Claude Cowork (Linux VM): installs xaffinity, fixes PATH
#
# NOTE: Does NOT export AFFINITY_API_KEY to the environment.
# The key stays in .env and is read per-command via --dotenv.
# This prevents the LLM from reading the key via `env` or `echo`.

# 1. Install xaffinity if not on PATH
if ! command -v xaffinity &>/dev/null; then
  # Try ~/.local/bin first (may already be installed but not on PATH)
  if [ -x "$HOME/.local/bin/xaffinity" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    pip install "affinity-sdk[cli]" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

# 2. Persist PATH for the session (Cowork sets CLAUDE_ENV_FILE; Claude Code does not)
if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qF '/.local/bin' "$CLAUDE_ENV_FILE" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
fi

# 3. Report status (non-blocking, stderr only)
# Uses --dotenv to check if .env has a valid key without exposing it
if ! command -v xaffinity &>/dev/null; then
  echo "xaffinity not available — install with: pip install 'affinity-sdk[cli]'" >&2
elif xaffinity --dotenv --json config check-key 2>/dev/null | grep -q '"configured":true\|"configured": true'; then
  echo "xaffinity ready (API key via --dotenv)" >&2
elif xaffinity --json config check-key 2>/dev/null | grep -q '"configured":true\|"configured": true'; then
  echo "xaffinity ready (API key from config)" >&2
else
  echo "xaffinity installed, no API key found — add AFFINITY_API_KEY to .env or run: xaffinity config setup-key" >&2
fi

exit 0
