#!/usr/bin/env python3
"""
Fix Rego v1 comprehension syntax
Changes := to = inside array/set comprehension bodies
"""

import sys
import re

def fix_comprehension_assignments(content):
    """
    Fix := to = inside comprehension bodies
    Pattern: [...|...] or {...|...}
    Inside the body (after |), change := to =
    """
    lines = content.split('\n')
    fixed_lines = []
    in_comprehension = False
    bracket_count = 0

    for i, line in enumerate(lines):
        # Track if we're inside a comprehension
        if '|' in line and ('[' in line or '{' in line):
            in_comprehension = True
            bracket_count = line.count('[') + line.count('{') - line.count(']') - line.count('}')
        elif in_comprehension:
            bracket_count += line.count('[') + line.count('{') - line.count(']') - line.count('}')
            if bracket_count <= 0:
                in_comprehension = False

        # If we're in a comprehension body (after |), replace := with =
        if in_comprehension and '|' not in line and ':=' in line:
            # Simple replacement: var := expr becomes var = expr
            line = re.sub(r'\b(\w+)\s*:=\s*', r'\1 = ', line)

        fixed_lines.append(line)

    return '\n'.join(fixed_lines)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: fix_rego_comprehensions.py <file>")
        sys.exit(1)

    filename = sys.argv[1]

    with open(filename, 'r') as f:
        content = f.read()

    fixed_content = fix_comprehension_assignments(content)

    with open(filename, 'w') as f:
        f.write(fixed_content)

    print(f"Fixed: {filename}")
