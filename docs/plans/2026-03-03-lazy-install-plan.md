# Lazy xaffinity CLI Installation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Defer pip install from SessionStart to first xaffinity use, eliminating ~30s overhead on every container start.

**Architecture:** Self-installing wrapper at `$user_bin/xaffinity` created by SessionStart; PreToolUse triggers it via session cache start and detects failures via marker file.

**Tech Stack:** Bash hooks, pip, pytest

**Design doc:** `docs/plans/2026-03-03-lazy-install-design.md`

---

### Task 1: Rewrite `session-setup.sh` (lightweight + wrapper creation)

**Files:**
- Modify: `plugins/xaffinity-cli/.claude-plugin/hooks/session-setup.sh` (full rewrite)

**Step 1: Write the new session-setup.sh**

Replace the entire file with:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Lightweight session setup — ensures PATH includes the Python user-bin dir
# and drops a self-installing wrapper if xaffinity is not on PATH.
#
# Heavy lifting (pip install, session cache) is deferred to pre-xaffinity.sh
# (PreToolUse hook) so it only runs when xaffinity is actually needed.
#
# Safe in all environments:
# - Claude Code (macOS): xaffinity already on PATH via pyenv — no-ops
# - Claude Desktop: not applicable (MCP server, not CLI)
# - Claude Cowork (Linux VM): creates wrapper, sets PATH (<100ms)
#
# NOTE: Does NOT export AFFINITY_API_KEY to the environment.
# The key stays in .env and is read per-command via --dotenv.
# This prevents the LLM from reading the key via `env` or `echo`.

# 1. Derive user-bin path (where pip --user installs scripts)
user_bin=$(python3 -c "import site, os; print(os.path.join(site.getuserbase(), 'bin'))" 2>/dev/null) || true
user_bin="${user_bin:-$HOME/.local/bin}"

# 2. Ensure the directory exists
mkdir -p "$user_bin"

# 3. Add to PATH in this process
if [[ ":$PATH:" != *":$user_bin:"* ]]; then
  export PATH="$user_bin:$PATH"
fi

# 4. Persist PATH for all tool calls in this session (unconditional — harmless
#    if dir is empty; ensures pip-installed binaries are found immediately)
if [ -n "${CLAUDE_ENV_FILE:-}" ] && ! grep -qF "$user_bin" "$CLAUDE_ENV_FILE" 2>/dev/null; then
  echo "export PATH=\"$user_bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# 5. If xaffinity is not available, drop a self-installing wrapper
if ! command -v xaffinity &>/dev/null; then
  # Clear stale state from previous sessions
  rm -f "$HOME/.xaffinity-install-status"
  rmdir "$HOME/.xaffinity-installing" 2>/dev/null || true

  cat > "$user_bin/xaffinity" << 'WRAPPER'
#!/bin/bash
set -euo pipefail

# Self-installing bootstrap wrapper for xaffinity CLI.
# Created by session-setup.sh at SessionStart.
# On first invocation: installs via pip, then exec's the real binary.
# pip install overwrites this wrapper with the real entry point.

# --- Recursion guard ---
if [ -n "${_XAFFINITY_BOOTSTRAP:-}" ]; then
  echo "error: xaffinity installation failed — run manually: pip install 'affinity-sdk[cli]'" >&2
  exit 1
fi
export _XAFFINITY_BOOTSTRAP=1

# --- Derive install paths (must match session-setup.sh) ---
user_bin=$(python3 -c "import site, os; print(os.path.join(site.getuserbase(), 'bin'))" 2>/dev/null) || true
user_bin="${user_bin:-$HOME/.local/bin}"

# --- Concurrency lock (mkdir is atomic) ---
lockdir="$HOME/.xaffinity-installing"
if mkdir "$lockdir" 2>/dev/null; then
  trap 'rmdir "$lockdir" 2>/dev/null || true' EXIT

  echo "Installing xaffinity CLI (first-time setup)..." >&2
  if ! pip install --user "affinity-sdk[cli]" >&2; then
    echo "INSTALL_FAILED" > "$HOME/.xaffinity-install-status"
    echo "error: pip install 'affinity-sdk[cli]' failed" >&2
    exit 1
  fi
  echo "INSTALLED" > "$HOME/.xaffinity-install-status"
else
  # Another process is installing — wait (no force-break, no retry)
  i=0
  while [ -d "$lockdir" ] && [ "$i" -lt 45 ]; do
    sleep 1
    i=$((i + 1))
  done

  # Check if the other process succeeded
  if grep -qF "INSTALLED" "$HOME/.xaffinity-install-status" 2>/dev/null; then
    exec "$user_bin/xaffinity" "$@"
  fi

  echo "error: xaffinity installation in progress or failed — retry shortly" >&2
  exit 1
fi

exec "$user_bin/xaffinity" "$@"
WRAPPER
  chmod +x "$user_bin/xaffinity"
fi

exit 0
```

**Step 2: Verify session-setup.sh is syntactically valid**

Run: `bash -n plugins/xaffinity-cli/.claude-plugin/hooks/session-setup.sh`
Expected: no output, exit 0

**Step 3: Commit**

```bash
git add plugins/xaffinity-cli/.claude-plugin/hooks/session-setup.sh
git commit -m "refactor(hooks): make SessionStart lightweight, defer pip install to wrapper"
```

---

### Task 2: Write tests for `session-setup.sh`

**Files:**
- Create: `tests/test_cli_session_setup_hook.py`

**Step 1: Write the test file**

```python
"""Tests for session-setup.sh hook."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

HOOK_PATH = str(
    Path(__file__).parent.parent
    / "plugins"
    / "xaffinity-cli"
    / ".claude-plugin"
    / "hooks"
    / "session-setup.sh"
)

_BASH = shutil.which("bash") or "/bin/bash"


def _run_hook(
    env_override: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run session-setup.sh with the given environment."""
    env = {**os.environ, **(env_override or {})}
    return subprocess.run(
        [_BASH, HOOK_PATH],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=False,
    )


@pytest.mark.req("CLI-SESSION-SETUP")
def test_noop_when_xaffinity_on_path():
    """When xaffinity is already on PATH, hook exits 0 and creates no wrapper."""
    result = _run_hook()
    assert result.returncode == 0


@pytest.mark.req("CLI-SESSION-SETUP")
def test_creates_wrapper_when_xaffinity_missing(tmp_path):
    """When xaffinity is not on PATH, hook creates a wrapper script."""
    user_bin = tmp_path / "bin"
    # Don't create user_bin — hook should mkdir it

    # Minimal PATH without xaffinity
    system_dirs = {"/bin", "/usr/bin"}
    minimal_path = os.pathsep.join(sorted(system_dirs))

    # Mock python3 to return our tmp_path as user base
    mock_python = tmp_path / "python3"
    mock_python.write_text(
        f'#!/bin/bash\necho "{tmp_path}"\n'
    )
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = {
        "PATH": f"{tmp_path}:{minimal_path}",
        "HOME": str(tmp_path),
    }
    result = _run_hook(env_override=env)
    assert result.returncode == 0

    wrapper = user_bin / "xaffinity"
    assert wrapper.exists(), "Wrapper should be created"
    assert wrapper.stat().st_mode & stat.S_IEXEC, "Wrapper should be executable"

    content = wrapper.read_text()
    assert "_XAFFINITY_BOOTSTRAP" in content, "Wrapper should have recursion guard"
    assert "pip install" in content, "Wrapper should install via pip"


@pytest.mark.req("CLI-SESSION-SETUP")
def test_clears_stale_marker_on_wrapper_creation(tmp_path):
    """When creating wrapper, stale install-status marker is cleared."""
    user_bin = tmp_path / "bin"

    # Create stale marker
    marker = tmp_path / ".xaffinity-install-status"
    marker.write_text("INSTALL_FAILED")

    # Mock python3
    mock_python = tmp_path / "python3"
    mock_python.write_text(
        f'#!/bin/bash\necho "{tmp_path}"\n'
    )
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    system_dirs = {"/bin", "/usr/bin"}
    minimal_path = os.pathsep.join(sorted(system_dirs))

    env = {
        "PATH": f"{tmp_path}:{minimal_path}",
        "HOME": str(tmp_path),
    }
    result = _run_hook(env_override=env)
    assert result.returncode == 0
    assert not marker.exists(), "Stale marker should be cleared"


@pytest.mark.req("CLI-SESSION-SETUP")
def test_writes_claude_env_file(tmp_path):
    """When CLAUDE_ENV_FILE is set, hook writes PATH to it."""
    env_file = tmp_path / "claude_env"
    env_file.write_text("")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "CLAUDE_ENV_FILE": str(env_file),
    }
    result = _run_hook(env_override=env)
    assert result.returncode == 0

    content = env_file.read_text()
    assert "PATH" in content, "Should write PATH to CLAUDE_ENV_FILE"
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_cli_session_setup_hook.py -v`
Expected: all 4 tests pass (the hook is already written from Task 1)

**Step 3: Commit**

```bash
git add tests/test_cli_session_setup_hook.py
git commit -m "test(hooks): add tests for lightweight session-setup.sh"
```

---

### Task 3: Update `pre-xaffinity.sh` (install-failure detection + session cache)

**Files:**
- Modify: `plugins/xaffinity-cli/.claude-plugin/hooks/pre-xaffinity.sh` (partial rewrite)

**Step 1: Write the updated pre-xaffinity.sh**

Replace the entire file with:

```bash
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

# --- Check for install failure (set by bootstrap wrapper) ---
if [ -f "$HOME/.xaffinity-install-status" ] && grep -qF "INSTALL_FAILED" "$HOME/.xaffinity-install-status" 2>/dev/null; then
  cat >&2 << 'EOF'
{
  "hookSpecificOutput": {
    "permissionDecision": "deny"
  },
  "systemMessage": "BLOCKED: xaffinity CLI installation failed. Ask the user to check network connectivity and Python environment, then run: pip install 'affinity-sdk[cli]'"
}
EOF
  exit 2
fi

# --- Start session cache if not already running ---
# On first use in a fresh container, this triggers the bootstrap wrapper
# which runs pip install (~30s) before the real xaffinity starts.
if [ -z "${AFFINITY_SESSION_CACHE:-}" ]; then
  cache_dir=$(xaffinity session start 2>/dev/null) || true
  if [ -n "${cache_dir:-}" ]; then
    export AFFINITY_SESSION_CACHE="$cache_dir"
    if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
      echo "export AFFINITY_SESSION_CACHE=\"$cache_dir\"" >> "$CLAUDE_ENV_FILE"
    fi
  fi

  # Re-check install status — wrapper may have just written INSTALL_FAILED
  if [ -f "$HOME/.xaffinity-install-status" ] && grep -qF "INSTALL_FAILED" "$HOME/.xaffinity-install-status" 2>/dev/null; then
    cat >&2 << 'EOF'
{
  "hookSpecificOutput": {
    "permissionDecision": "deny"
  },
  "systemMessage": "BLOCKED: xaffinity CLI installation failed. Ask the user to check network connectivity and Python environment, then run: pip install 'affinity-sdk[cli]'"
}
EOF
    exit 2
  fi
fi

# Config/help commands are always allowed (after install check, before API key)
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
```

**Step 2: Verify syntax**

Run: `bash -n plugins/xaffinity-cli/.claude-plugin/hooks/pre-xaffinity.sh`
Expected: no output, exit 0

**Step 3: Run existing tests to verify no regressions**

Run: `pytest tests/test_cli_pre_xaffinity_hook.py -v`
Expected: all 6 existing tests pass (API key validation logic is unchanged)

**Step 4: Commit**

```bash
git add plugins/xaffinity-cli/.claude-plugin/hooks/pre-xaffinity.sh
git commit -m "feat(hooks): add install-failure detection and lazy session cache to PreToolUse"
```

---

### Task 4: Add tests for install-failure detection in `pre-xaffinity.sh`

**Files:**
- Modify: `tests/test_cli_pre_xaffinity_hook.py` — add new tests

**Step 1: Add install-failure marker test**

Append after the existing tests (after line 159):

```python
@pytest.mark.req("CLI-PRETOOL-HOOK")
def test_hook_denies_when_install_failed(tmp_path):
    """Hook denies xaffinity commands when install-status marker says INSTALL_FAILED."""
    # Create INSTALL_FAILED marker
    marker = tmp_path / ".xaffinity-install-status"
    marker.write_text("INSTALL_FAILED")

    # Create a mock xaffinity so command -v succeeds (wrapper would be on PATH)
    mock_bin = tmp_path / "xaffinity"
    mock_bin.write_text("#!/bin/bash\nexit 1\n")
    mock_bin.chmod(mock_bin.stat().st_mode | stat.S_IEXEC)

    jq_dir = str(Path(shutil.which("jq") or "/usr/bin/jq").parent)
    system_dirs = {jq_dir, "/bin", "/usr/bin"}
    minimal_path = os.pathsep.join([str(tmp_path), *sorted(system_dirs)])

    env = {"PATH": minimal_path, "HOME": str(tmp_path)}
    result = _run_hook(
        "xaffinity --readonly person ls --json",
        env_override=env,
        cwd=str(tmp_path),
    )
    assert result.returncode == 2
    assert "installation failed" in result.stderr.lower()


@pytest.mark.req("CLI-PRETOOL-HOOK")
def test_hook_allows_when_install_succeeded(tmp_path):
    """Hook proceeds normally when install-status marker says INSTALLED."""
    # Create INSTALLED marker
    marker = tmp_path / ".xaffinity-install-status"
    marker.write_text("INSTALLED")

    # Create mock xaffinity that reports key configured
    mock_bin = tmp_path / "xaffinity"
    mock_bin.write_text(
        textwrap.dedent("""\
        #!/bin/bash
        if [[ "$*" == *"session start"* ]]; then
            echo "/tmp/fake-cache"
        else
            echo '{"data":{"configured":true}}'
        fi
    """)
    )
    mock_bin.chmod(mock_bin.stat().st_mode | stat.S_IEXEC)

    jq_dir = str(Path(shutil.which("jq") or "/usr/bin/jq").parent)
    system_dirs = {jq_dir, "/bin", "/usr/bin"}
    minimal_path = os.pathsep.join([str(tmp_path), *sorted(system_dirs)])

    env = {"PATH": minimal_path, "HOME": str(tmp_path)}
    result = _run_hook(
        "xaffinity --readonly person ls --json",
        env_override=env,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0
```

**Step 2: Run all pre-xaffinity tests**

Run: `pytest tests/test_cli_pre_xaffinity_hook.py -v`
Expected: all 8 tests pass (6 existing + 2 new)

**Step 3: Commit**

```bash
git add tests/test_cli_pre_xaffinity_hook.py
git commit -m "test(hooks): add install-failure marker detection tests"
```

---

### Task 5: Update `hooks.json` timeouts

**Files:**
- Modify: `plugins/xaffinity-cli/.claude-plugin/hooks/hooks.json`

**Step 1: Update timeouts and status message**

In `hooks.json`, make three changes:
- Line 11: `"timeout": 60` → `"timeout": 10`
- Line 12: `"statusMessage": "Setting up Affinity CLI..."` → `"statusMessage": "Preparing Affinity CLI environment..."`
- Line 34: `"timeout": 10` → `"timeout": 60`

The resulting file should be:

```json
{
  "description": "Bootstrap xaffinity CLI, guard API keys, and validate commands",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/session-setup.sh",
            "timeout": 10,
            "statusMessage": "Preparing Affinity CLI environment..."
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/guard-env-read.sh",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/pre-xaffinity.sh",
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

**Step 2: Validate JSON syntax**

Run: `python3 -m json.tool plugins/xaffinity-cli/.claude-plugin/hooks/hooks.json > /dev/null`
Expected: exit 0, no output

**Step 3: Commit**

```bash
git add plugins/xaffinity-cli/.claude-plugin/hooks/hooks.json
git commit -m "chore(hooks): adjust timeouts — SessionStart 10s, PreToolUse 60s"
```

---

### Task 6: Register new test marker and run full suite

**Files:**
- Check: `pyproject.toml` for marker registration

**Step 1: Check if CLI-SESSION-SETUP marker needs registration**

Search `pyproject.toml` for the `markers` section under `[tool.pytest.ini_options]`. If `CLI-SESSION-SETUP` is not listed, add it alongside the existing markers.

**Step 2: Run the full test suite**

Run: `pytest tests/test_cli_pre_xaffinity_hook.py tests/test_cli_session_setup_hook.py -v`
Expected: all tests pass

**Step 3: Regenerate requirements mapping**

Run: `python tools/generate_requirements_mapping.py`
Expected: `docs/internal/requirements_to_tests_mapping.md` is updated

**Step 4: Commit if mapping changed**

```bash
git add pyproject.toml docs/internal/requirements_to_tests_mapping.md
git commit -m "chore: register CLI-SESSION-SETUP marker, update requirements mapping"
```

---

### Task 7: Update skill documentation

**Files:**
- Modify: `plugins/xaffinity-cli/.claude-plugin/skills/xaffinity-cli-usage/SKILL.md:15-30`

**Step 1: Update the "session cache" reference**

The skill currently says "Session cache: Set up automatically at session start." Update to reflect that session cache is now started on first xaffinity use (PreToolUse hook), not at session start.

Search the skill file for any mention of "session start" or "session cache" and update the description to say the session cache is started automatically on first use.

**Step 2: Commit**

```bash
git add plugins/xaffinity-cli/.claude-plugin/skills/xaffinity-cli-usage/SKILL.md
git commit -m "docs(skill): update session cache description for lazy init"
```
