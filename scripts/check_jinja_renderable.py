#!/usr/bin/env python3
"""Every Jinja expression in the Ansible tree must at least lex.

WHY THIS EXISTS
---------------
Six templates in this repository could never render. Each was a task that
failed the moment it was reached, and several had been that way for months --
two fact-gathering roles had never produced the facts they exist to produce.

ansible-lint does detect this class, but its failure mode is to CRASH: an
unlexable template raises out of Jinja's tokenizer, the traceback replaces the
report, and every other finding in the run is lost. That is how these six
stayed hidden. One of them was hiding the other five.

This check does the same thing deliberately and reports all of them at once,
with the file and the path to the offending value.

WHAT IT CATCHES, WITH THE REAL EXAMPLES
---------------------------------------
1. An escaped quote inside a Jinja expression:

       shell: >
         ... {{ x | default(\\"ACCOUNT_ID\\") }} ...

   In a BLOCK SCALAR, YAML performs no unescaping, so Jinja receives a literal
   backslash and its lexer rejects it. The same text inside a DOUBLE-QUOTED
   scalar is fine, because YAML unescapes it first -- which is why this cannot
   be found by grep. Only parsing the YAML and lexing the resulting value
   distinguishes the two.

2. Operators Jinja does not have:

       {% if (mode | int) & 0o007 > 0 %}

   There is no bitwise AND in Jinja, and `0o007` is not Jinja syntax.

WHAT IT DOES NOT CATCH
----------------------
Lexing is not rendering. An expression that lexes can still fail on an
undefined variable, a missing filter, or a type error at runtime. This is the
cheap structural half; it is not a substitute for running the playbook.
"""

import pathlib
import sys

import yaml

try:
    from jinja2 import Environment
except ImportError:
    print("jinja2 not installed — skipping (pip install jinja2)", file=sys.stderr)
    sys.exit(0)

REPO = pathlib.Path(__file__).resolve().parent.parent
ROOTS = ["ansible"]

env = Environment()


def walk(value, path, findings, filename):
    """Depth-first over the parsed YAML, lexing every string that templates."""
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            try:
                list(env.lex(value))
            except Exception as exc:  # noqa: BLE001 — any lexer failure is a finding
                findings.append((filename, path, str(exc).splitlines()[0],
                                 value.strip()[:100]))
    elif isinstance(value, dict):
        for key, sub in value.items():
            walk(sub, f"{path}.{key}", findings, filename)
    elif isinstance(value, list):
        for i, sub in enumerate(value):
            walk(sub, f"{path}[{i}]", findings, filename)


def main() -> int:
    findings = []
    scanned = 0

    for root in ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for f in sorted(list(base.rglob("*.yml")) + list(base.rglob("*.yaml"))):
            try:
                docs = list(yaml.safe_load_all(f.read_text(encoding="utf-8")))
            except Exception:
                continue          # YAML parse errors belong to the parse check
            scanned += 1
            rel = f.relative_to(REPO)
            for doc in docs:
                walk(doc, "", findings, str(rel))

    # Tripwire, same reasoning as the other gates here: a check that silently
    # stops scanning must fail rather than pass. Reporting "0 problems" after
    # examining nothing is worse than reporting a problem.
    if scanned < 100:
        print(f"FAIL: only {scanned} YAML files scanned — expected several hundred.")
        print("The file walk is broken; this check would otherwise pass vacuously.")
        return 1

    print(f"lexed every Jinja expression in {scanned} YAML files")

    if findings:
        print(f"\nFAIL: {len(findings)} template(s) cannot be rendered\n")
        for filename, path, err, snippet in findings:
            print(f"  {filename}{path}")
            print(f"      {err}")
            print(f"      {snippet}")
        print("\nA template that does not lex is a task that cannot run. Common causes:")
        print("  - \\\" inside a {{ }} expression in a block scalar — YAML does not")
        print("    unescape there, so Jinja sees a literal backslash. Name the quote")
        print("    as a variable instead, or restructure so no quote is needed.")
        print("  - operators Jinja does not have: & | ^ for bitwise, 0o777 literals.")
        return 1

    print("OK: every Jinja expression lexes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
