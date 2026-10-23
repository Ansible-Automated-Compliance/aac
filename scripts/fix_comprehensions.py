#!/usr/bin/env python3
import os
import re
import glob

def fix_file(filepath):
    """Fix common comprehension syntax issues in a single file"""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Pattern 1: all([condition | var := array[_]]) -> count([var | var := array[_]; condition]) == count(array)
        # This is a simple heuristic fix - may need manual review for complex cases
        
        # Pattern 2: Fix function definitions without 'if'
        content = re.sub(r'^([a-zA-Z_][a-zA-Z0-9_]*\([^)]*\)) := ([^{]+) {', r'\1 := \2 if {', content, flags=re.MULTILINE)
        
        if content != original_content:
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"Fixed: {filepath}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Fix comprehension syntax errors in all Rego files"""
    fixed_count = 0
    
    for filepath in glob.glob("policies/**/*.rego", recursive=True):
        if fix_file(filepath):
            fixed_count += 1
    
    print(f"Fixed {fixed_count} files")

if __name__ == "__main__":
    main()