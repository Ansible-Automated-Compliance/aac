#!/usr/bin/env python3
"""Verify every relative markdown link in tracked docs resolves to a file.

The failure class: docs/DOCUMENTATION_INDEX.md carried 67 dead links —
the index was the least reliable document in the repository (handover
audit v1.1). This gate keeps internal links honest from now on.

Checked: [text](relative/path) links in tracked *.md files.
Skipped: http(s)/mailto links, pure #anchors, and links inside fenced
code blocks. Anchors on file links (file.md#section) are checked for
the file only.

Exit 0 = all resolve; 1 = dead links found.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def main() -> int:
    tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout.split()
    dead = []
    checked = 0
    for rel in tracked:
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        # strip fenced code blocks so example links don't count
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            checked += 1
            target_path = target.split("#", 1)[0]
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            if not resolved.exists():
                dead.append(f"{rel}: ({target})")
    print(f"checked {checked} relative links across {len(tracked)} markdown files")
    for d in dead:
        print(f"DEAD LINK: {d}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
