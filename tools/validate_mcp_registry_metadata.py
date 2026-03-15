#!/usr/bin/env python3
"""
Validate MCP Registry metadata consistency across sources.

Checks that mcp/server.json, mcp/mcpb.conf, and
mcp/server.d/server.meta.json stay aligned on key fields:
  - Server name suffix
  - Title
  - Repository / documentation URLs

This script has no dependencies beyond the Python stdlib so it
can run in any CI environment.

Usage:
    python tools/validate_mcp_registry_metadata.py [--verbose]

Exit codes:
    0 - All metadata is consistent
    1 - Inconsistencies found
    2 - File read / parse error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent / "mcp"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_mcpb_conf(path: Path) -> dict[str, str]:
    """Parse shell-style KEY=\"value\" assignments from mcpb.conf."""
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([A-Z_]+)="(.*)"$', line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def load_json(path: Path) -> dict:  # type: ignore[type-arg]
    """Load a JSON file, returning the parsed dict."""
    return json.loads(path.read_text())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_name(
    server_json: dict,  # type: ignore[type-arg]
    mcpb_conf: dict[str, str],
    meta_json: dict,  # type: ignore[type-arg]
    errors: list[str],
) -> None:
    """Registry name must end with the MCPB_NAME / meta name."""
    registry_name: str = server_json.get("name", "")
    mcpb_name = mcpb_conf.get("MCPB_NAME", "")
    meta_name: str = meta_json.get("name", "")

    if mcpb_name and not registry_name.endswith(f"/{mcpb_name}"):
        errors.append(
            f"server.json name '{registry_name}' does not end "
            f"with '/{mcpb_name}' (from mcpb.conf MCPB_NAME)"
        )
    if meta_name and not registry_name.endswith(f"/{meta_name}"):
        errors.append(
            f"server.json name '{registry_name}' does not end "
            f"with '/{meta_name}' (from server.meta.json name)"
        )
    if mcpb_name and meta_name and mcpb_name != meta_name:
        errors.append(
            f"mcpb.conf MCPB_NAME='{mcpb_name}' differs from server.meta.json name='{meta_name}'"
        )


def check_title(
    server_json: dict,  # type: ignore[type-arg]
    meta_json: dict,  # type: ignore[type-arg]
    errors: list[str],
) -> None:
    """Title should match server.meta.json."""
    sj_title: str = server_json.get("title", "")
    meta_title: str = meta_json.get("title", "")
    if sj_title and meta_title and sj_title != meta_title:
        errors.append(
            f"server.json title '{sj_title}' differs from server.meta.json title '{meta_title}'"
        )


def check_urls(
    server_json: dict,  # type: ignore[type-arg]
    mcpb_conf: dict[str, str],
    errors: list[str],
) -> None:
    """Repository and documentation URLs should align."""
    repo_url = (server_json.get("repository") or {}).get("url", "")
    mcpb_repo = mcpb_conf.get("MCPB_REPOSITORY", "")
    if repo_url and mcpb_repo and repo_url != mcpb_repo:
        errors.append(
            f"server.json repository.url '{repo_url}' differs "
            f"from mcpb.conf MCPB_REPOSITORY '{mcpb_repo}'"
        )

    website_url: str = server_json.get("websiteUrl", "")
    mcpb_docs = mcpb_conf.get("MCPB_DOCUMENTATION", "")
    # websiteUrl (project website) and MCPB_DOCUMENTATION (MCP docs)
    # may legitimately differ when the MCP server lives in a repo
    # subfolder — only flag if they share no common base.
    if (
        website_url
        and mcpb_docs
        and not mcpb_docs.startswith(website_url)
        and not website_url.startswith(mcpb_docs)
    ):
        errors.append(
            f"server.json websiteUrl '{website_url}' and "
            f"mcpb.conf MCPB_DOCUMENTATION '{mcpb_docs}' "
            f"share no common URL base"
        )


def check_description_length(
    server_json: dict,  # type: ignore[type-arg]
    errors: list[str],
) -> None:
    """MCP Registry schema limits description to 100 chars."""
    desc: str = server_json.get("description", "")
    if len(desc) > 100:
        errors.append(f"server.json description is {len(desc)} chars (max 100 per registry schema)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate MCP Registry metadata consistency")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each check result",
    )
    args = parser.parse_args()

    server_json_path = MCP_DIR / "server.json"
    mcpb_conf_path = MCP_DIR / "mcpb.conf"
    meta_json_path = MCP_DIR / "server.d" / "server.meta.json"

    for p in (server_json_path, mcpb_conf_path, meta_json_path):
        if not p.exists():
            print(f"ERROR: required file not found: {p}", file=sys.stderr)
            return 2

    try:
        server_json = load_json(server_json_path)
        mcpb_conf = parse_mcpb_conf(mcpb_conf_path)
        meta_json = load_json(meta_json_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: failed to parse metadata files: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []

    check_name(server_json, mcpb_conf, meta_json, errors)
    check_title(server_json, meta_json, errors)
    check_urls(server_json, mcpb_conf, errors)
    check_description_length(server_json, errors)

    if args.verbose:
        print(f"Checked: {server_json_path}")
        print(f"         {mcpb_conf_path}")
        print(f"         {meta_json_path}")

    if errors:
        print(
            f"\n{len(errors)} metadata inconsistenc{'y' if len(errors) == 1 else 'ies'} found:\n",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("MCP Registry metadata: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
