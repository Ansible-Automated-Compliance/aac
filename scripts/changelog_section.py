#!/usr/bin/env python3
"""Print one version's section of CHANGELOG.md to stdout.

    python3 scripts/changelog_section.py 2.9.0 > /tmp/relnotes.md
    gh release create v2.9.0 --title "AAC v2.9.0" --notes-file /tmp/relnotes.md

Exists because the release step in RELEASING.md previously showed
`--notes-file <(...)` as a placeholder, which is not a runnable command. A
release process whose commands cannot be copy-pasted is a process that gets
improvised, and improvised releases are what this repository is trying to stop
doing.

Exits non-zero with a clear message if the version has no section, so a release
cannot be published with empty notes because someone forgot the changelog entry.
"""

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = REPO / "CHANGELOG.md"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <version>   e.g. 2.9.0", file=sys.stderr)
        return 2

    version = sys.argv[1].lstrip("v")

    if not CHANGELOG.exists():
        print(f"{CHANGELOG} not found", file=sys.stderr)
        return 1

    text = CHANGELOG.read_text(encoding="utf-8")

    # Match from this version's heading up to the next version heading. The
    # lookahead stops at `## [` rather than `##` so subsections inside the entry
    # (### Added, ### Fixed) do not truncate it.
    pattern = rf"^## \[{re.escape(version)}\].*?(?=^## \[|\Z)"
    match = re.search(pattern, text, re.S | re.M)

    if not match:
        print(f"No CHANGELOG entry for {version}.", file=sys.stderr)
        print("Add one before cutting the release — see RELEASING.md.", file=sys.stderr)
        available = re.findall(r"^## \[([^\]]+)\]", text, re.M)
        if available:
            print(f"Sections present: {', '.join(available)}", file=sys.stderr)
        return 1

    section = match.group(0).strip()

    # A heading with no body underneath it is an entry someone forgot to write.
    body = re.sub(r"^## \[[^\]]+\][^\n]*\n", "", section).strip()
    if not body:
        print(f"CHANGELOG entry for {version} is empty.", file=sys.stderr)
        return 1

    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
