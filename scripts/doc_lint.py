#!/usr/bin/env python3
"""
Document Linter/Fixer

Detects and optionally fixes missing document metadata (doc_id, doc_type, applies_to).
Supports YAML frontmatter and standardized header blocks.

Usage:
    python doc_lint.py --check /path/to/docs    # Check mode (CI)
    python doc_lint.py --fix /path/to/docs      # Fix mode (local)
    python doc_lint.py --diff /path/to/docs     # Show diffs only

Environment:
    None required
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Error: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)


# Document type detection patterns
DOC_TYPE_PATTERNS = {
    "spec": [r"\bPRD\b", r"\bspec\b", r"requirements?\b", r"\bspecification\b"],
    "decision": [r"\bADR\b", r"\bARD\b", r"decision\b", r"architecture.*decision"],
    "report": [r"\bAAR\b", r"\breport\b", r"after.?action", r"post.?mortem"],
    "runbook": [r"runbook\b", r"operations?\b", r"playbook\b", r"how.?to"],
    "use_case": [r"use.?case\b", r"scenario\b", r"user.?story"],
    "guide": [r"guide\b", r"tutorial\b", r"getting.?started"],
    "reference": [r"reference\b", r"api\b", r"schema\b"],
    "architecture": [r"architecture\b", r"design\b", r"system\b"],
}

# Standard header block pattern
HEADER_BLOCK_PATTERN = re.compile(
    r"^<!--\s*DOC_META\s*\n(.*?)\n\s*-->\s*$",
    re.MULTILINE | re.DOTALL
)


@dataclass
class LintIssue:
    """A lint issue found in a document."""
    file_path: str
    issue_type: str  # missing_frontmatter, missing_doc_id, missing_doc_type, etc.
    message: str
    suggestion: str = ""
    line: int = 0
    fixable: bool = True


@dataclass
class LintResult:
    """Result of linting a set of documents."""
    issues: list[LintIssue] = field(default_factory=list)
    files_checked: int = 0
    files_with_issues: int = 0


def parse_frontmatter(content: str) -> tuple[dict, str, int]:
    """Parse YAML frontmatter from document content.

    Returns: (frontmatter_dict, body, frontmatter_end_line)
    """
    if not content.startswith("---"):
        return {}, content, 0

    lines = content.split("\n")
    end_idx = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        return {}, content, 0

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return {}, content, 0

    return frontmatter, body, end_idx + 1


def parse_header_block(content: str) -> tuple[dict, str]:
    """Parse DOC_META header block from document content."""
    match = HEADER_BLOCK_PATTERN.search(content)
    if not match:
        return {}, content

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, content

    # Remove header block from content
    body = content[:match.start()] + content[match.end():]
    return meta, body.strip()


def infer_doc_type(file_path: Path, content: str) -> str:
    """Infer document type from filename and content."""
    filename = file_path.name.lower()
    text = (filename + " " + content[:2000]).lower()

    for doc_type, patterns in DOC_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return doc_type

    return "unknown"


def infer_doc_id(file_path: Path) -> str:
    """Infer document ID from filename."""
    stem = file_path.stem
    # Convert to kebab-case
    doc_id = re.sub(r"[^a-zA-Z0-9\s-]", "", stem)
    doc_id = re.sub(r"[\s_]+", "-", doc_id)
    return doc_id.lower().strip("-")


def lint_document(file_path: Path) -> list[LintIssue]:
    """Lint a single document for missing metadata."""
    issues = []
    rel_path = str(file_path)

    try:
        content = file_path.read_text()
    except Exception as e:
        issues.append(LintIssue(
            file_path=rel_path,
            issue_type="read_error",
            message=f"Could not read file: {e}",
            fixable=False,
        ))
        return issues

    # Try to parse existing metadata
    frontmatter, body, fm_end = parse_frontmatter(content)
    header_meta, _ = parse_header_block(content)

    # Merge metadata sources
    meta = {**header_meta, **frontmatter}

    # Check for missing doc_id
    if "doc_id" not in meta:
        suggested_id = infer_doc_id(file_path)
        issues.append(LintIssue(
            file_path=rel_path,
            issue_type="missing_doc_id",
            message="Missing doc_id in frontmatter",
            suggestion=f"doc_id: {suggested_id}",
        ))

    # Check for missing doc_type
    if "doc_type" not in meta:
        suggested_type = infer_doc_type(file_path, content)
        issues.append(LintIssue(
            file_path=rel_path,
            issue_type="missing_doc_type",
            message="Missing doc_type in frontmatter",
            suggestion=f"doc_type: {suggested_type}",
        ))

    # Check for missing title
    if "title" not in meta:
        # Try to extract from first H1
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            suggested_title = h1_match.group(1).strip()
        else:
            suggested_title = file_path.stem.replace("-", " ").title()
        issues.append(LintIssue(
            file_path=rel_path,
            issue_type="missing_title",
            message="Missing title in frontmatter",
            suggestion=f"title: \"{suggested_title}\"",
        ))

    return issues


def generate_frontmatter_fix(file_path: Path, issues: list[LintIssue]) -> str | None:
    """Generate fixed content with frontmatter added/updated."""
    content = file_path.read_text()
    frontmatter, body, fm_end = parse_frontmatter(content)

    # Collect fixes
    fixes = {}
    for issue in issues:
        if issue.suggestion:
            key, _, value = issue.suggestion.partition(": ")
            if key and value:
                # Parse the value
                if value.startswith('"') and value.endswith('"'):
                    fixes[key] = value[1:-1]
                else:
                    fixes[key] = value

    if not fixes:
        return None

    # Merge with existing frontmatter
    new_fm = {**frontmatter, **fixes}

    # Generate new content
    if frontmatter:
        # Replace existing frontmatter
        lines = content.split("\n")
        fm_yaml = yaml.dump(new_fm, default_flow_style=False, sort_keys=True).strip()
        new_content = "---\n" + fm_yaml + "\n---\n" + body
    else:
        # Add new frontmatter
        fm_yaml = yaml.dump(new_fm, default_flow_style=False, sort_keys=True).strip()
        new_content = "---\n" + fm_yaml + "\n---\n\n" + content

    return new_content


def lint_directory(path: Path, patterns: list[str] = None) -> LintResult:
    """Lint all documents in a directory."""
    result = LintResult()
    patterns = patterns or ["**/*.md"]

    files_with_issues = set()

    for pattern in patterns:
        for file_path in path.glob(pattern):
            if not file_path.is_file():
                continue
            if ".git" in str(file_path) or "node_modules" in str(file_path):
                continue

            result.files_checked += 1
            issues = lint_document(file_path)

            if issues:
                files_with_issues.add(str(file_path))
                result.issues.extend(issues)

    result.files_with_issues = len(files_with_issues)
    return result


def print_issues(result: LintResult, show_suggestions: bool = True) -> None:
    """Print lint issues to stdout."""
    if not result.issues:
        print(f"✓ No issues found in {result.files_checked} files")
        return

    # Group by file
    by_file = {}
    for issue in result.issues:
        if issue.file_path not in by_file:
            by_file[issue.file_path] = []
        by_file[issue.file_path].append(issue)

    print(f"Found {len(result.issues)} issues in {result.files_with_issues} files:\n")

    for file_path, issues in sorted(by_file.items()):
        print(f"  {file_path}:")
        for issue in issues:
            print(f"    - {issue.message}")
            if show_suggestions and issue.suggestion:
                print(f"      Suggestion: {issue.suggestion}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Document metadata linter")
    parser.add_argument(
        "path",
        type=Path,
        help="Path to documents (file or directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode - report issues without fixing (for CI)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix mode - automatically fix issues",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show diffs for fixes without applying",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        help="Glob pattern for files to lint (default: **/*.md)",
    )
    args = parser.parse_args()

    if not args.check and not args.fix and not args.diff:
        args.check = True  # Default to check mode

    # Lint
    if args.path.is_file():
        result = LintResult(files_checked=1)
        issues = lint_document(args.path)
        if issues:
            result.issues = issues
            result.files_with_issues = 1
    else:
        result = lint_directory(args.path, args.pattern)

    # Output
    if args.json:
        output = {
            "files_checked": result.files_checked,
            "files_with_issues": result.files_with_issues,
            "issues": [
                {
                    "file": i.file_path,
                    "type": i.issue_type,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "fixable": i.fixable,
                }
                for i in result.issues
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print_issues(result)

    # Apply fixes if requested
    if args.fix or args.diff:
        # Group issues by file for fixing
        by_file = {}
        for issue in result.issues:
            if not issue.fixable:
                continue
            if issue.file_path not in by_file:
                by_file[issue.file_path] = []
            by_file[issue.file_path].append(issue)

        fixes_applied = 0
        for file_path, issues in by_file.items():
            path = Path(file_path)
            new_content = generate_frontmatter_fix(path, issues)

            if new_content:
                if args.diff:
                    print(f"\n--- {file_path}")
                    print(f"+++ {file_path} (fixed)")
                    # Simple diff display
                    old_lines = path.read_text().split("\n")[:20]
                    new_lines = new_content.split("\n")[:20]
                    for i, (old, new) in enumerate(zip(old_lines, new_lines)):
                        if old != new:
                            print(f"-{old}")
                            print(f"+{new}")
                    print("...")
                elif args.fix:
                    path.write_text(new_content)
                    print(f"  Fixed: {file_path}")
                    fixes_applied += 1

        if args.fix:
            print(f"\n✓ Applied fixes to {fixes_applied} files")

    # Exit code
    if args.check and result.issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
