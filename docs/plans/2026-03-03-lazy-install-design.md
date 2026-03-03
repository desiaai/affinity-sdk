# Lazy xaffinity CLI Installation

## Problem

The xaffinity-cli plugin's `SessionStart` hook runs `pip install "affinity-sdk[cli]"` unconditionally on every container start, adding ~30s overhead even when the agent never uses xaffinity. In ephemeral containers (Cowork, NanoClaw), packages aren't persisted between starts.

## Solution

Defer pip install to first actual xaffinity use via a **self-installing wrapper** created at session start, with **hook-side awareness** of install status for correct error reporting.

Two components work together:

1. **SessionStart** (`session-setup.sh`) drops a tiny shell wrapper at the user-bin path that makes `command -v xaffinity` succeed immediately. No pip install, no session cache, no status report. Runs in <100ms.

2. **PreToolUse** (`pre-xaffinity.sh`) triggers the wrapper on first use (via session cache start), detects install failures via a marker file, and surfaces specific errors.

## Architecture

### The wrapper

Created by `session-setup.sh` when `command -v xaffinity` fails. On first invocation:

```
caller invokes xaffinity
  └─ wrapper runs
     ├─ recursion guard (_XAFFINITY_BOOTSTRAP env var)
     ├─ mkdir lock (prevents concurrent installs)
     ├─ pip install --user "affinity-sdk[cli]"
     │   ├─ success → writes INSTALLED marker, pip overwrites wrapper with real binary
     │   └─ failure → writes INSTALL_FAILED marker, exits 1
     ├─ lock released (trap on EXIT)
     └─ exec real xaffinity with original args
```

Concurrent invocations wait on the lock with a 45s timeout. After timeout, the waiter checks the marker — if `INSTALLED`, exec real binary; otherwise exit with error. The waiter does NOT force-break the lock or retry install.

### session-setup.sh (SessionStart)

```
1. Derive user_bin from python3 site.getuserbase() (fallback: ~/.local/bin)
2. mkdir -p $user_bin
3. Write PATH=$user_bin:$PATH to CLAUDE_ENV_FILE (unconditionally)
4. If command -v xaffinity fails:
   a. Clear stale marker file (rm -f)
   b. Clear stale lock dir (rmdir)
   c. Write wrapper script to $user_bin/xaffinity
5. exit 0
```

Clearing stale markers/locks on session start ensures transient failures in session N don't poison session N+1. Safe because in all target runtimes, $HOME is per-container (Cowork) or xaffinity is pre-installed and no wrapper is created (macOS).

### pre-xaffinity.sh (PreToolUse)

```
1. Not an xaffinity command? → exit 0 (<1ms)
2. Install failure marker exists? → deny with INSTALL-specific error
3. Start session cache: xaffinity session start
   (triggers wrapper on first use → pip install ~30s → real xaffinity)
4. Re-check install failure marker (wrapper may have just set it) → deny if failed
5. Config/help command? → exit 0 (skip API key check)
6. API key validation (unchanged — three-tier check)
```

Session cache start (step 3) is the natural trigger for the wrapper. All xaffinity commands — including help/config — go through the same install path for consistent diagnostics.

### hooks.json changes

- SessionStart timeout: 60 → 10 (lightweight now)
- SessionStart statusMessage: updated to reflect lightweight operation
- PreToolUse Bash timeout: 10 → 60 (accommodates pip install via session cache)

## Environment behavior

| Environment | SessionStart | First xaffinity command | Subsequent |
|---|---|---|---|
| macOS Claude Code | No-op (xaffinity on PATH via pyenv) | Session cache + API check | Fast path |
| Cowork (fresh) | Creates wrapper, sets PATH (~100ms) | Wrapper installs (~30s), session cache, API check | Fast path |
| Non-Affinity session | Creates wrapper, sets PATH (~100ms) | Never fires | N/A |

## Error handling

| Failure | Behavior |
|---|---|
| pip fails (network) | Wrapper writes INSTALL_FAILED. Hook denies with install-specific error. Next session clears marker, retries. |
| pip killed (SIGKILL) | No marker written, lock may be stale. Waiter times out, fails. Next session clears lock, retries. |
| pip slow (>45s) | Waiter times out, fails. Original install keeps running. Next invocation finds INSTALLED marker, works. |
| Concurrent commands | Second wrapper waits on lock. Sees INSTALLED → exec, or times out → fails cleanly. No concurrent pip installs. |
| PYTHONUSERBASE override | Dynamic user_bin derivation handles it. pip --user installs to correct location. |

## Files changed

1. `plugins/xaffinity-cli/.claude-plugin/hooks/session-setup.sh` — rewrite (remove pip install, add wrapper creation)
2. `plugins/xaffinity-cli/.claude-plugin/hooks/pre-xaffinity.sh` — add install-failure detection and session cache start
3. `plugins/xaffinity-cli/.claude-plugin/hooks/hooks.json` — update timeouts
4. `tests/test_cli_pre_xaffinity_hook.py` — add tests for install failure marker detection
5. New: `tests/test_cli_session_setup_hook.py` — tests for wrapper creation and PATH setup

## Design decisions

- **Wrapper over deny-and-retry**: Avoids depending on LLM retry behavior. The wrapper makes `command -v xaffinity` succeed immediately, so no deny message is needed.
- **Session cache triggers install**: Natural first-use initialization point — no separate install step in the hook.
- **No lock force-break**: Prevents re-introducing the concurrent pip install race. Waiters fail cleanly; next session clears stale locks.
- **Marker cleared on session start**: Prevents transient failures from poisoning future sessions. Safe because $HOME is per-container in all target runtimes where the wrapper is used.
- **Unified install path for all commands**: Help/config commands also go through session cache start. Adds one-time latency but provides consistent error handling.
