#!/usr/bin/env python3
"""Static checks for playbook contracts that ansible-lint does not cover.

WHY THIS EXISTS
---------------
ansible-lint catches malformed Ansible. It does not catch a playbook that is
perfectly valid and silently targets the wrong machine.

The defect that motivated this: three patch playbooks selected their hosts with

    hosts: "{{ target_hostname | default('localhost') }}"

while the workflow and every survey passed `target_host`. Jinja resolved the
undefined name to the default, so backup, install and assurance all ran inside
the execution environment instead of on the host being patched. Nothing was
malformed. Lint was clean. It surfaced only because the EE has no `sudo` — with
sudo present all three would have "succeeded" and been wrong, producing a
recovery point and an assurance pass for a machine nobody touched.

Two rules, both aimed at that class:

  HOSTS-FALLBACK   a play with `become: true` whose `hosts` falls back to
                   localhost. Escalating privilege on the controller when a
                   variable is missing is never the intent.

  HOSTS-UNDECLARED a variable used in `hosts:` that nothing in the repo appears
                   to supply. Catches the typo/rename class directly.

Exit 0 clean, 1 on findings.
"""
from __future__ import annotations
import re
import sys
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PLAYBOOKS = sorted((REPO / "ansible" / "playbooks").glob("*.yml"))

# Where a `hosts:` variable can legitimately be SUPPLIED from. This is wider
# than the set of files being checked, and deliberately so: an EDA rulebook
# passing extra_vars is a real supply source, and scanning only
# ansible/playbooks made `host_target` look undeclared when
# extensions/eda/rulebooks/lab10_itsm_ticket_handler.yml sets it three times.
# A checker that reports a false positive on a correct playbook is a checker
# people learn to skip.
SUPPLY_SOURCES = (
    PLAYBOOKS
    + sorted((REPO / "extensions").rglob("*.yml"))
    + sorted((REPO / "ansible" / "eda").rglob("*.yml"))
    + sorted((REPO / "ansible" / "tasks").rglob("*.yml"))
    + sorted((REPO / "ansible" / "roles").rglob("*.yml"))
)

# A var is "supplied" if it appears anywhere as an assignment, a survey field, a
# set_stats key, or an extra_vars key — anywhere other than the hosts: line itself.
SUPPLY_PAT = "|".join([
    r"{var}\s*:",           # yaml key / play var / extra_vars
    r"\"{var}\"\s*:",       # json extra_vars
    r"'{var}'\s*:",
    r"-e\s+{var}=",         # cli
    r"variable\W+{var}",    # survey spec
])


def find_plays(text: str):
    """Yield (line_no, hosts_expr, play_block) for each play in a playbook."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"\s*hosts:\s*(.+?)\s*(?:#.*)?$", line)
        if not m:
            continue
        # play block = from here to the next top-level "- name:" or EOF
        block = []
        for nxt in lines[i:]:
            if block and re.match(r"^- ", nxt):
                break
            block.append(nxt)
        yield i + 1, m.group(1).strip(), "\n".join(block)


def main() -> int:
    corpus = "\n".join(p.read_text(errors="ignore") for p in SUPPLY_SOURCES)
    findings: list[str] = []

    for pb in PLAYBOOKS:
        try:
            text = pb.read_text(errors="ignore")
        except OSError:
            continue
        rel = pb.relative_to(REPO)

        for lineno, hosts, block in find_plays(text):
            if "{{" not in hosts:
                continue
            vars_used = re.findall(r"\b([a-z_][a-z0-9_]*)\s*\|", hosts)
            vars_used += re.findall(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", hosts)
            vars_used = [v for v in dict.fromkeys(vars_used) if v not in ("default",)]

            # RULE 1 — privilege escalation with a localhost fallback.
            # Match the DEFAULT VALUE specifically, not the mere presence of the
            # word: `hostvars['localhost'][...] | default('none')` is a lookup, not
            # a fallback, and flagging it would train people to ignore this gate.
            defaults_to_localhost = re.search(
                r"\|\s*default\(\s*['\"]localhost['\"]", hosts)
            if defaults_to_localhost and re.search(r"^\s*become:\s*(true|yes)", block, re.M):
                findings.append(
                    f"{rel}:{lineno} [HOSTS-FALLBACK] play uses `become` but `hosts` "
                    f"falls back to localhost — a missing variable will escalate "
                    f"privilege on the controller instead of targeting a host.\n"
                    f"    hosts: {hosts}"
                )

            # RULE 2 — a hosts variable nothing supplies
            for v in vars_used:
                pat = "|".join(SUPPLY_PAT.format(var=re.escape(v)).split("|"))
                # exclude the hosts: lines themselves from the corpus search
                corpus_wo_hosts = re.sub(r"^\s*hosts:.*$", "", corpus, flags=re.M)
                if not re.search(pat, corpus_wo_hosts):
                    findings.append(
                        f"{rel}:{lineno} [HOSTS-UNDECLARED] `hosts` uses `{v}`, which "
                        f"nothing in the repo appears to set. If the caller passes a "
                        f"different name, this play silently targets its default.\n"
                        f"    hosts: {hosts}"
                    )

    if findings:
        print(f"Playbook contract violations: {len(findings)}\n")
        for f in findings:
            print("  " + f.replace("\n", "\n  "))
            print()
        return 1

    print(f"Playbook contracts OK ({len(PLAYBOOKS)} playbooks checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
