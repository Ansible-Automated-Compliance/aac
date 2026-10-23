#!/usr/bin/env python3
"""
Automated Rego Policy Fixer
Fixes common OPA 1.9.0 compatibility issues
"""

import re
import sys
from pathlib import Path


def fix_array_concat_sets(content):
    """Fix array.concat being called on sets instead of arrays"""
    # Pattern: array.concat(set1, set2) should convert sets to arrays first
    # This is complex, so we'll look for array.concat with set comprehensions

    # For now, we'll identify lines that need manual fixing
    issues = []
    for i, line in enumerate(content.split('\n'), 1):
        if 'array.concat' in line and '[v |' not in line and '[violation |' not in line:
            # Likely calling array.concat on a set/rule reference
            if 'violations' in line or '.report' in line:
                issues.append((i, line.strip()))

    return content, issues


def fix_time_diff_arity(content):
    """Fix time.diff() arity mismatch - OPA 1.9.0 requires 3 arguments"""
    # time.diff(t1, t2) -> time.diff(t1, t2, "nanoseconds")

    pattern = r'time\.diff\(([^,]+),\s*([^)]+)\)'
    replacement = r'time.diff(\1, \2, "nanoseconds")'

    fixed_content = re.sub(pattern, replacement, content)

    changes = len(re.findall(pattern, content))
    return fixed_content, changes


def fix_missing_if_keyword(content):
    """Add missing 'if' keywords before rule bodies"""
    lines = content.split('\n')
    fixed_lines = []

    for i, line in enumerate(lines):
        # Pattern: rule_name {
        # Should be: rule_name if {
        if re.match(r'^(\w+)\s+\{$', line.strip()) and not line.strip().startswith('some '):
            # Check if previous line is not a rule definition
            if i > 0 and not lines[i-1].strip().endswith('{'):
                fixed_line = line.replace(' {', ' if {')
                fixed_lines.append(fixed_line)
                continue

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def fix_partial_set_contains(content):
    """Fix partial set rules to use 'contains' keyword"""
    lines = content.split('\n')
    fixed_lines = []

    for line in lines:
        # Pattern: rule_name[item] {
        # Should be: rule_name contains item if {
        match = re.match(r'^(\s*)(\w+)\[(\w+)\]\s*\{', line)
        if match:
            indent, rule_name, item = match.groups()
            fixed_line = f"{indent}{rule_name} contains {item} if {{"
            fixed_lines.append(fixed_line)
            continue

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)


def analyze_file(filepath):
    """Analyze a file and suggest fixes"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except Exception as e:
        return None, f"Error reading file: {e}"

    fixes_applied = []
    issues_found = []

    # Fix time.diff arity
    content, time_diff_count = fix_time_diff_arity(content)
    if time_diff_count > 0:
        fixes_applied.append(f"Fixed {time_diff_count} time.diff() calls")

    # Fix missing if keywords
    original_content = content
    content = fix_missing_if_keyword(content)
    if content != original_content:
        fixes_applied.append("Added missing 'if' keywords")

    # Fix partial set contains
    original_content = content
    content = fix_partial_set_contains(content)
    if content != original_content:
        fixes_applied.append("Fixed partial set rules with 'contains'")

    # Check for array.concat issues
    content, array_issues = fix_array_concat_sets(content)
    if array_issues:
        issues_found.append(f"Found {len(array_issues)} potential array.concat issues (manual fix needed)")
        for line_no, line_content in array_issues[:3]:  # Show first 3
            issues_found.append(f"  Line {line_no}: {line_content}")

    return content, fixes_applied, issues_found


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_rego_policies.py <policy_file> [--dry-run]")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv

    if not filepath.exists():
        print(f"Error: File {filepath} does not exist")
        sys.exit(1)

    print(f"Analyzing {filepath}...")

    result = analyze_file(filepath)
    if result[0] is None:
        print(result[1])
        sys.exit(1)

    new_content, fixes_applied, issues_found = result

    if fixes_applied:
        print("\nFixes applied:")
        for fix in fixes_applied:
            print(f"  ✓ {fix}")

    if issues_found:
        print("\nIssues requiring manual review:")
        for issue in issues_found:
            print(f"  ⚠ {issue}")

    if not fixes_applied and not issues_found:
        print("No issues found!")
        sys.exit(0)

    if dry_run:
        print("\n[DRY RUN] Would write changes to file")
    else:
        try:
            with open(filepath, 'w') as f:
                f.write(new_content)
            print(f"\n✓ Changes written to {filepath}")
        except Exception as e:
            print(f"\nError writing file: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
