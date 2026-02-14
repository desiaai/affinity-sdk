#!/usr/bin/env bash
set -euo pipefail

# Bootstrap xaffinity CLI for Cowork sessions.
# Safe in all environments: only acts when something is missing.
# - Claude Code (macOS): xaffinity already installed, key in config.toml/env — no-ops
# - Claude Desktop: not applicable (MCP server, not CLI)
# - Claude Cowork (Linux VM): installs xaffinity, fixes PATH, loads .env key

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

# 3. Load API key from .env if not already set
if [ -z "${AFFINITY_API_KEY:-}" ]; then
  ENV_FILE=""

  # Check standard locations
  for candidate in ".env" "${CLAUDE_PROJECT_DIR:-.}/.env"; do
    if [ -f "$candidate" ]; then
      ENV_FILE="$candidate"
      break
    fi
  done

  # Cowork session mounts (only if standard locations didn't work)
  if [ -z "$ENV_FILE" ] && [ -d "/sessions" ]; then
    ENV_FILE=$(find /sessions/*/mnt -maxdepth 3 -name ".env" -type f 2>/dev/null | head -1)
  fi

  if [ -n "$ENV_FILE" ] && [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -q 'AFFINITY_API_KEY' "$CLAUDE_ENV_FILE" 2>/dev/null; then
    KEY=$(grep -E '^AFFINITY_API_KEY=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    KEY="${KEY%$'\r'}"  # Strip trailing \r from Windows-style CRLF
    # Strip surrounding quotes (single or double) that .env files often use
    KEY="${KEY#\"}" && KEY="${KEY%\"}"
    KEY="${KEY#\'}" && KEY="${KEY%\'}"
    if [ -n "$KEY" ]; then
      echo "export AFFINITY_API_KEY=\"$KEY\"" >> "$CLAUDE_ENV_FILE"
    fi
  fi
fi

# 4. Report status (non-blocking, stderr only)
if ! command -v xaffinity &>/dev/null; then
  echo "xaffinity not available — install with: pip install 'affinity-sdk[cli]'" >&2
elif [ -n "${AFFINITY_API_KEY:-}" ]; then
  echo "xaffinity ready (API key from environment)" >&2
elif xaffinity --json config check-key 2>/dev/null | grep -q '"configured":true\|"configured": true'; then
  echo "xaffinity ready (API key from config)" >&2
else
  echo "xaffinity installed, no API key found — run: xaffinity config setup-key" >&2
fi

exit 0
