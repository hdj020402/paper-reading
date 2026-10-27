#!/usr/bin/env python3
"""Check markdown files for hard-wrapped prose.

Prose (in Chinese or any language) must be one paragraph per line; a
line ends only at its paragraph's end. A paragraph is a maximal block
of consecutive non-blank, non-exempt lines; a block longer than one
line is flagged, except for tables, whose rows all share the pipe
prefix. Lists, code, headings, blockquotes, comments, and frontmatter
are exempt.

Usage: .venv/bin/python scripts/md-lint.py [FILE ...]
  With files: check those files. Without: check README.md, AGENTS.md, and
  every review note under resources/reviews/ (bundle contents and the
  vendored skill are out of scope).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXEMPT_PREFIXES = ("#", "-", "*", "|", ">", "```", "<!--", "[comment]:", "!", "Peak:")


def is_exempt(stripped: str) -> bool:
    return not stripped or stripped.startswith(EXEMPT_PREFIXES)


def lint_file(path: Path) -> list[int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    problems: list[int] = []
    in_code = False
    in_frontmatter = path.suffix == ".md" and lines[:1] == ["---"]
    block: list[int] = []

    def flush() -> None:
        nonlocal block
        # A multi-line prose block: every line after the first is a wrap.
        if len(block) > 1:
            problems.extend(block[1:])
        block = []

    for i, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        if in_frontmatter:
            if i > 1 and stripped == "---":
                in_frontmatter = False
            continue
        if is_exempt(stripped):
            flush()
            continue
        # Ordered-flow steps (pipelines) and numeric prose lines are
        # formatting, not wrapped paragraphs.
        if re.match(r"^\d+\.\s", stripped) or re.match(r"^\d+\s+`", stripped):
            flush()
            continue
        block.append(i)
    flush()
    return problems


def default_files() -> list[Path]:
    candidates = [ROOT / "README.md", ROOT / "AGENTS.md"]
    candidates.extend(sorted((ROOT / "resources" / "reviews").glob("*.md")))
    return [p for p in candidates if p.is_file()]


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--check"]
    paths = [Path(a) for a in args] if args else default_files()
    issues = 0
    for path in paths:
        for line_no in lint_file(path):
            print(f"{path}: line {line_no}: hard-wrapped prose: line joins the previous line; merge into one paragraph line")
            issues += 1
    if issues:
        print(f"{issues} hard-wrap issue(s) found. Prose is one paragraph per line.", file=sys.stderr)
        return 1
    print(f"OK: {len(paths)} file(s), no hard-wrapped prose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
