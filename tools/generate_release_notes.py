"""Generate structured release notes from CHANGELOG.md entries.

Reads a Keep-a-Changelog file, extracts the section for a given
version, and restructures it into a user-facing release notes
format suitable for GitHub Releases.

Usage:
    python tools/generate_release_notes.py --version 1.5.2 --type sdk
    python tools/generate_release_notes.py --version 1.18.1 --type mcp
    python tools/generate_release_notes.py --version 1.5.2 --type sdk \
        --mcpb-url "https://..." --output release_notes.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SDK_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
MCP_CHANGELOG = REPO_ROOT / "mcp" / "CHANGELOG.md"

SDK_FOOTER_TEMPLATE = REPO_ROOT / ".github" / "release-install-footer.md"
MCP_FOOTER_TEMPLATE = REPO_ROOT / ".github" / "mcp-release-install-footer.md"

# Keep-a-Changelog section headings and their mapping
# to the output format.
HEADING_MAP: dict[str, str] = {
    "highlights": "Highlights",
    "added": "What's New",
    "changed": "Changes",
    "changed (breaking)": "Breaking Changes",
    "removed": "Removed",
    "fixed": "Bug Fixes",
    "performance": "Performance",
    "documentation": "Documentation",
    "known issues": "Known Issues",
    "improved": "Improvements",
    "compatibility": "Compatibility",
    "cli prerequisites (implemented)": "CLI Prerequisites",
    "cli compatibility": "CLI Compatibility",
}

# Output ordering for sections
SECTION_ORDER = [
    "Highlights",
    "Breaking Changes",
    "What's New",
    "Changes",
    "Removed",
    "Bug Fixes",
    "Performance",
    "Improvements",
    "Documentation",
    "Known Issues",
    "Compatibility",
    "CLI Compatibility",
    "CLI Prerequisites",
]


def extract_version_section(
    changelog_path: Path,
    version: str,
) -> str | None:
    """Extract the changelog section for a specific version.

    Handles both ``## [1.5.2] - date`` and ``## 0.14.0 - date``
    formats.  Returns the section body (everything between the
    version heading and the next version heading), or ``None``
    if the version is not found.
    """
    text = changelog_path.read_text(encoding="utf-8")
    escaped = re.escape(version)
    # Match "## [1.5.2] - 2026-..." or "## 1.5.2 - 2026-..."
    pattern = rf"^## \[?{escaped}\]? - .+$"
    lines = text.splitlines()

    start_idx: int | None = None
    end_idx: int | None = None

    for i, line in enumerate(lines):
        if start_idx is None:
            if re.match(pattern, line):
                start_idx = i + 1
        # Next version heading ends this section
        elif re.match(r"^## \[?\d", line):
            end_idx = i
            break

    if start_idx is None:
        return None

    if end_idx is None:
        end_idx = len(lines)

    section = "\n".join(lines[start_idx:end_idx]).strip()
    return section if section else None


def _classify_heading(raw: str) -> str:
    """Map a raw ### heading to the output section name."""
    normalized = raw.strip().lower()
    if normalized in HEADING_MAP:
        return HEADING_MAP[normalized]
    return raw.strip()


def _is_breaking_item(text: str) -> bool:
    """Check if a changelog bullet point describes a breaking change."""
    lower = text.lower()
    return (
        lower.startswith("- **breaking")
        or lower.startswith("- **breaking:**")
        or "**breaking**" in lower
    )


def parse_sections(body: str) -> dict[str, list[str]]:
    """Parse a changelog section body into categorized sections.

    Returns a dict mapping section names (from HEADING_MAP) to
    lists of content lines (including bullet points).

    Any text before the first ``###`` heading is captured as a
    preamble and prepended to the Highlights section.
    """
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    current_lines: list[str] = []
    preamble_lines: list[str] = []

    for line in body.splitlines():
        heading_match = re.match(r"^### (.+)$", line)
        if heading_match:
            # Save previous section
            if current_heading is not None:
                sections[current_heading] = current_lines
            current_heading = _classify_heading(heading_match.group(1))
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)
        else:
            # Text before first ### heading
            preamble_lines.append(line)

    # Save last section
    if current_heading is not None:
        sections[current_heading] = current_lines

    # Prepend preamble to Highlights if it has content
    preamble_text = "\n".join(preamble_lines).strip()
    if preamble_text:
        existing = sections.get("Highlights", [])
        sections["Highlights"] = [preamble_text, "", *existing] if existing else [preamble_text]

    # Post-process: move breaking items from "Changes" to
    # "Breaking Changes"
    if "Changes" in sections:
        breaking_lines: list[str] = []
        non_breaking_lines: list[str] = []
        for line in sections["Changes"]:
            if _is_breaking_item(line):
                breaking_lines.append(line)
            else:
                non_breaking_lines.append(line)
        if breaking_lines:
            existing = sections.get("Breaking Changes", [])
            sections["Breaking Changes"] = existing + breaking_lines
            sections["Changes"] = non_breaking_lines

    return sections


def format_release_notes(
    sections: dict[str, list[str]],
) -> str:
    """Format parsed sections into the target release notes layout."""
    parts: list[str] = []

    for section_name in SECTION_ORDER:
        if section_name not in sections:
            continue
        lines = sections[section_name]
        # Skip empty sections (only whitespace lines)
        content = "\n".join(lines).strip()
        if not content:
            continue
        parts.append(f"## {section_name}\n\n{content}")

    # Collect any sections not in SECTION_ORDER
    for section_name, lines in sections.items():
        if section_name in SECTION_ORDER:
            continue
        content = "\n".join(lines).strip()
        if not content:
            continue
        parts.append(f"## {section_name}\n\n{content}")

    return "\n\n".join(parts)


def generate_sdk_footer(mcpb_url: str | None = None) -> str:
    """Generate the SDK install footer, optionally with MCPB URL."""
    if not SDK_FOOTER_TEMPLATE.exists():
        return ""
    footer = SDK_FOOTER_TEMPLATE.read_text(encoding="utf-8")
    if mcpb_url:
        footer = footer.replace("{{MCPB_URL}}", mcpb_url)
    return footer


def generate_mcp_footer() -> str:
    """Generate the MCP install footer."""
    if not MCP_FOOTER_TEMPLATE.exists():
        return ""
    return MCP_FOOTER_TEMPLATE.read_text(encoding="utf-8")


def generate_release_notes(
    version: str,
    release_type: str,
    mcpb_url: str | None = None,
) -> str:
    """Generate complete release notes for a version.

    Args:
        version: Version string (e.g. "1.5.2").
        release_type: Either "sdk" or "mcp".
        mcpb_url: Optional MCPB download URL (SDK releases only).

    Returns:
        Complete markdown release notes with footer.
    """
    if release_type == "sdk":
        changelog_path = SDK_CHANGELOG
    elif release_type == "mcp":
        changelog_path = MCP_CHANGELOG
    else:
        raise ValueError(f"Unknown release type: {release_type}")

    body = extract_version_section(changelog_path, version)
    if body is None:
        print(
            f"::warning::No changelog entry found for {release_type} version {version}",
            file=sys.stderr,
        )
        notes = f"Release {version}"
    else:
        sections = parse_sections(body)
        notes = format_release_notes(sections)

        if "Highlights" not in sections:
            print(
                f"::warning::No ### Highlights section found for {release_type} version {version}",
                file=sys.stderr,
            )

    # Append footer
    footer = generate_sdk_footer(mcpb_url) if release_type == "sdk" else generate_mcp_footer()

    return f"{notes}\n{footer}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate release notes from CHANGELOG.md",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version to generate notes for (e.g. 1.5.2)",
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["sdk", "mcp"],
        dest="release_type",
        help="Release type: sdk or mcp",
    )
    parser.add_argument(
        "--mcpb-url",
        default=None,
        help="MCPB download URL (SDK releases only)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    notes = generate_release_notes(
        version=args.version,
        release_type=args.release_type,
        mcpb_url=args.mcpb_url,
    )

    if args.output:
        Path(args.output).write_text(notes, encoding="utf-8")
        print(f"Release notes written to {args.output}")
    else:
        print(notes)


if __name__ == "__main__":
    main()
