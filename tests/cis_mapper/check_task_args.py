#!/usr/bin/env python3
"""Every free-form shell/command task must survive Ansible's own argument splitter.

An odd apostrophe in a comment ("user's") makes split_args raise "unbalanced
jinja2 block or quotes" at run time, which neither the shell test nor the
mapper harness exercises.  Usage: check_task_args.py <tasks.yml> [...]
"""
import sys

import yaml
from ansible.parsing.splitter import split_args

bad = 0
for path in sys.argv[1:]:
    for task in yaml.safe_load(open(path)) or []:
        for key in ("shell", "ansible.builtin.shell", "command", "ansible.builtin.command"):
            arg = task.get(key)
            if isinstance(arg, str):
                try:
                    split_args(arg)
                except Exception as exc:  # AnsibleParserError
                    bad += 1
                    print(f"FAIL {path}: {task.get('name', '?')}: {str(exc).splitlines()[0][:100]}")
print(f"task args: {'FAIL' if bad else 'ok'} ({bad} failing)")
sys.exit(1 if bad else 0)
