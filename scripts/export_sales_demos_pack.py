#!/usr/bin/env python3
"""Assemble the AAC pack (published as ynotbhatc/aac-pack) from ansible/ao/sales_demos_pack.yml.

    python3 scripts/export_sales_demos_pack.py --repo . --out /tmp/pack

Copies the manifest's playbooks, vars, files, trees and extra files into
<out>/, preserving the playbooks/ vars/ files/ sibling layout the playbooks
rely on, follows ../files and ../vars references found inside exported
playbooks, applies the manifest's rewrites, writes MANIFEST.yml (source
commit and its commit date, every file with its sha256, anything requested
but missing) and README.md, and then runs the forbidden-pattern sweep over
EVERY file in the output tree — the copied content and the generated
metadata alike. Any hit REFUSES the export (exit 2).

Fail-closed rules:
  * a file whose suffix is not a known text type is a violation unless the
    manifest lists its destination path under ``allowed_binary``; allowed
    binaries are still scanned byte-wise for the forbidden patterns;
  * nothing volatile is written: two exports of the same source commit are
    byte-identical, so the sync playbook's "nothing changed" check is real.

Pure stdlib plus PyYAML, so it runs in the execution environment and on a
laptop alike. No network.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys

import yaml

TEXT_EXT = {".yml", ".yaml", ".rego", ".sql", ".json", ".md", ".j2", ".py", ".sh", ".txt", ".cfg"}
REF_RE = re.compile(r"\.\./(files|vars|templates)/([A-Za-z0-9_./-]+)")
GENERATED = ("MANIFEST.yml", "README.md")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # not a checkout, or no git: still export, say so
        return ""


def sweep(out, forbidden, allowed_binary):
    """Scan every file under ``out``. Returns a sorted list of violation strings.

    Text files are scanned line by line. A file with an unknown suffix is a
    violation in itself unless its path is in ``allowed_binary``, in which
    case its bytes are decoded leniently and scanned the same way.
    """
    violations = []
    for root, _, names in os.walk(out):
        for n in names:
            path = os.path.join(root, n)
            rel = os.path.relpath(path, out)
            ext = os.path.splitext(n)[1]
            if ext in TEXT_EXT:
                with open(path, errors="ignore") as f:
                    text = f.read()
            elif rel in allowed_binary:
                with open(path, "rb") as f:
                    text = f.read().decode("utf-8", errors="ignore")
            else:
                violations.append(
                    f"{rel}: unsupported file type {ext or '(none)'!r} is not scrubbed — "
                    "ship it as a text type or list it under allowed_binary in the manifest"
                )
                continue
            for i, line in enumerate(text.splitlines(), 1):
                for pat in forbidden:
                    if pat.search(line):
                        violations.append(f"{rel}:{i}: /{pat.pattern}/")
    return sorted(violations)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="compliance repository root")
    ap.add_argument("--out", required=True, help="output directory (replaced)")
    ap.add_argument("--manifest", default="ansible/ao/sales_demos_pack.yml")
    ap.add_argument("--source-commit", default="",
                    help="the source commit when --repo is not a git checkout (an AAP project "
                         "directory has no .git; the job provides awx_project_revision)")
    ap.add_argument("--source-committed-at", default="",
                    help="that commit's committer date (ISO 8601); with --source-commit, "
                         "replaces git log")
    ap.add_argument("--source-branch", default="", help="with --source-commit, replaces git rev-parse")
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    out = os.path.abspath(args.out)
    manifest_path = os.path.join(repo, args.manifest)
    if not os.path.isfile(manifest_path):          # a manifest from another checkout
        manifest_path = os.path.abspath(args.manifest)
    with open(manifest_path) as f:
        m = yaml.safe_load(f)

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    copied = {}   # dest relative -> source relative
    missing = []

    def put(src_rel, dest_rel):
        src = os.path.join(repo, src_rel)
        if not os.path.isfile(src):
            missing.append(src_rel)
            return
        dest = os.path.join(out, dest_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        # copy (not copy2): content only, no source mtimes, so the tree is a
        # pure function of the source commit.
        shutil.copy(src, dest)
        copied[dest_rel] = src_rel

    for p in m.get("playbooks", []):
        put(p, "playbooks/" + os.path.basename(p))
    for v in m.get("vars", []):
        put(v, "vars/" + os.path.basename(v))
    for fpath in m.get("files", []):
        put(fpath, "files/" + os.path.basename(fpath))
    for t in m.get("trees", []):
        src_dir = os.path.join(repo, t["src"])
        if not os.path.isdir(src_dir):
            missing.append(t["src"] + "/")
            continue
        for root, _, names in os.walk(src_dir):
            for n in sorted(names):
                rel = os.path.relpath(os.path.join(root, n), src_dir)
                put(os.path.join(t["src"], rel), os.path.join(t["dest"], rel))
    for e in m.get("extra_files", []):
        put(e["src"], e["dest"])

    # Follow ../files, ../vars, ../templates references inside exported playbooks.
    for dest_rel, src_rel in list(copied.items()):
        if not dest_rel.startswith("playbooks/"):
            continue
        with open(os.path.join(out, dest_rel), errors="ignore") as f:
            text = f.read()
        for kind, name in REF_RE.findall(text):
            if name in ("vault_secrets.yml", "site_config.yml"):   # deliberately absent (gitignored by design)
                continue
            src_dir = os.path.dirname(src_rel)
            candidate = os.path.normpath(os.path.join(src_dir, "..", kind, name))
            dest = os.path.join(kind, name)
            if dest in copied or candidate in missing:
                continue
            put(candidate, dest)

    # Rewrites (text files only; binaries are never rewritten).
    rewrites = m.get("rewrites", [])
    if rewrites:
        for dest_rel in sorted(copied):
            path = os.path.join(out, dest_rel)
            if os.path.splitext(path)[1] not in TEXT_EXT:
                continue
            with open(path, errors="ignore") as f:
                text = f.read()
            new = text
            for rw in rewrites:
                new = new.replace(rw["match"], rw["replace"])
            if new != text:
                with open(path, "w") as f:
                    f.write(new)

    # Provenance. Deterministic for a given source commit: the commit's own
    # committer date stands in for "generated at", so an unchanged source
    # produces a byte-identical tree and the sync's no-change check holds.
    # Provenance comes from the checkout when there is one, and from the
    # caller when there is not: an AAP job's project directory carries no
    # .git, so without --source-commit the manifest would say ''.
    commit = args.source_commit or git(repo, "rev-parse", "HEAD")
    committed_at = args.source_committed_at or git(repo, "log", "-1", "--format=%cI", "HEAD")
    branch = args.source_branch or git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if not commit:
        print("export: source commit unknown — --repo is not a git checkout and --source-commit "
              "was not given; the manifest would carry no provenance", file=sys.stderr)
        return 3
    manifest = {
        "pack_version": m.get("pack_version", 1),
        "source": {
            "repository": "ansible-automated-compliance/aac",
            "commit": commit,
            "committed_at": committed_at,
            "branch": branch,
        },
        "files": {d: {"source": s, "sha256": sha256(os.path.join(out, d))} for d, s in sorted(copied.items())},
        "missing": sorted(set(missing)),
    }
    with open(os.path.join(out, "MANIFEST.yml"), "w") as f:
        f.write("# GENERATED by ansible-automated-compliance/aac scripts/export_sales_demos_pack.py — do not edit.\n")
        yaml.safe_dump(manifest, f, sort_keys=False, width=120)

    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(f"""# aac-pack

**The Ansible Automated Compliance (AAC) pack**: the playbooks, OPA routing
policies, Automation Orchestrator workflow definitions, evidence-database
schema and dashboards that partner demo platforms consume. Published from the
private `ansible-automated-compliance/aac` repository by its `scripts/export_sales_demos_pack.py`;
this copy is from commit `{commit[:12] or 'unknown'}` (committed {committed_at or 'unknown'}).
**Pin a tag.** `main` moves with every sync; a tag never does.

This repository is generated. Edit the source there; a change made here is
overwritten by the next sync. `MANIFEST.yml` lists every file with its source
path and sha256. The export refuses to publish if a lab identifier, a
secret-shaped string or a customer name survives in the tree.

| Directory | What it is |
|---|---|
| `playbooks/` | The AAC playbooks a consuming platform runs as job templates (an AAP project pointed at this repository at a tag, `playbook: playbooks/<name>.yml`) |
| `vars/`, `files/` | What those playbooks read relative to themselves; `vault_secrets.yml` and `site_config.yml` are deliberately absent, the consuming platform's credentials and extra vars supply values |
| `roles/aac_compliance_db/` | The evidence-database schema as the product applies it (`tasks/schema.yml`) |
| `opa-routing/policies/` | The AO decision policies: the policy decides, the model only recommends |
| `ao/workflows/`, `ao/components.yml` | The AO workflow definitions as the AO API returns them, and what each needs, including the agentic nodes' tool-access posture |
| `grafana/` | AAC dashboards over the evidence database |

Consumers: [ericcames/sales.demos](https://github.com/ericcames/sales.demos)
(plan and phases: sales.demos#841; the pin is its `aac_pack_version`).
The vendor-neutral policy library is separate and also public:
[ynotbhatc/rego_policy_libraries](https://github.com/ynotbhatc/rego_policy_libraries).
""")

    # The forbidden sweep runs LAST, over everything in the tree — including
    # the metadata just written, so a private branch name or a slipped value
    # in the generated files is caught the same as in the copied ones.
    forbidden = [re.compile(p) for p in m.get("forbidden_patterns", [])]
    allowed_binary = set(m.get("allowed_binary", []) or [])
    violations = sweep(out, forbidden, allowed_binary)

    print(f"pack: {len(copied)} files -> {out}")
    if missing:
        print("MISSING (requested, not found in source):")
        for x in sorted(set(missing)):
            print("  -", x)
    if violations:
        print("FORBIDDEN PATTERNS FOUND — export refused:", file=sys.stderr)
        for v in violations:
            print("  -", v, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
