#!/usr/bin/env python3
"""Validate local Markdown links and heading anchors without network access."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
EXTERNAL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//")


def slugify(heading: str) -> str:
    """Return the GitHub-style fragment id for a Markdown heading."""
    text = re.sub(r"`([^`]*)`", r"\1", heading).strip().lower()
    return "".join(
        char if char.isalnum() or char in " -_" else "" for char in text
    ).replace(" ", "-")


def headings_for(path: Path) -> set[str]:
    """Collect heading ids while ignoring fenced code blocks."""
    headings: set[str] = set()
    duplicate_counts: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = slugify(match.group(1))
        count = duplicate_counts.get(base, 0)
        duplicate_counts[base] = count + 1
        headings.add(base if count == 0 else f"{base}-{count}")
    return headings


def validate_document(path: Path, root: Path) -> tuple[int, list[str]]:
    """Validate local links in one Markdown document against the checkout."""
    errors: list[str] = []
    checked = 0
    heading_cache: dict[Path, set[str]] = {path: headings_for(path)}
    in_fence = False
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for raw_destination in LINK_RE.findall(line):
            destination = raw_destination.strip().strip("<>")
            if not destination or EXTERNAL_RE.match(destination):
                continue
            target_text, separator, fragment = destination.partition("#")
            target = (
                (path.parent / urllib.parse.unquote(target_text)).resolve()
                if target_text
                else path
            )
            checked += 1
            try:
                target.relative_to(root)
            except ValueError:
                errors.append(
                    f"{path}:{line_number}: link escapes repository: {destination}"
                )
                continue
            if not target.exists():
                errors.append(
                    f"{path}:{line_number}: missing link target: {destination}"
                )
                continue
            if separator and fragment:
                if target.suffix.lower() != ".md":
                    errors.append(
                        f"{path}:{line_number}: fragment target is not Markdown: {destination}"
                    )
                    continue
                anchors = heading_cache.setdefault(target, headings_for(target))
                anchor = urllib.parse.unquote(fragment)
                if anchor not in anchors:
                    errors.append(
                        f"{path}:{line_number}: missing heading anchor: {destination}"
                    )
    return checked, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "documents", nargs="+", type=Path, help="Markdown file(s) to validate"
    )
    args = parser.parse_args()
    root = Path.cwd().resolve()
    checked = 0
    errors: list[str] = []
    for document in args.documents:
        path = document.resolve()
        if not path.is_file() or path.suffix.lower() != ".md":
            errors.append(f"{document}: expected an existing Markdown file")
            continue
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"{document}: document is outside the repository")
            continue
        document_checked, document_errors = validate_document(path, root)
        checked += document_checked
        errors.extend(document_errors)
    if errors:
        print("Documentation validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentation validation passed: {checked} local link(s) checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
