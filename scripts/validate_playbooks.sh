#!/usr/bin/env bash
# validate_playbooks.sh — the Ansible-layer validation gate.
#
# Every defect found in the August 2026 demo-readiness work was in the Ansible
# layer, and that layer had no automated checking of any kind. The Rego library
# has `opa test`. The playbooks had nothing.
#
# Run locally before pushing. CI runs the same checks via
# .github/workflows/ansible-validation.yml -- it does NOT invoke this script,
# so a check added here must be added there too. This header previously
# claimed CI parity that did not exist.
#
#   ./scripts/validate_playbooks.sh
#
# Exit 0 = clean. Non-zero = at least one check failed.

set -uo pipefail
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

FAILED=0
hr() { printf '%s\n' "------------------------------------------------------------"; }

# Needed by EVERY step, not just lint. Without it ansible-playbook fails at parse
# time on an unknown module and never reaches the behaviour under test — which is
# how the fail-closed check below reported a false failure the first time it ran.
export ANSIBLE_COLLECTIONS_PATH="${ANSIBLE_COLLECTIONS_PATH:-$HOME/.ansible/collections}"

# ---------------------------------------------------------------------------
# 1. ansible-lint
#
# Catches malformed Ansible, including Jinja template errors. This is the check
# that would have caught the A0 assurance bug: `#` used as a comment inside a
# {{ }} expression made the whole template unrenderable, and the node could
# never run. `ansible-playbook --syntax-check` PASSES that file; lint exits 2.
# ---------------------------------------------------------------------------
hr; echo "1/7  ansible-lint"; hr
if command -v ansible-lint >/dev/null 2>&1; then
  # Public collections only — a validation gate must not require an Automation
  # Hub token. Config lives in .ansible-lint (offline: true).
  for c in community.postgresql community.general ansible.posix ansible.utils \
           ansible.windows community.windows kubernetes.core; do
    ansible-galaxy collection install "$c" -p ~/.ansible/collections >/dev/null 2>&1 || true
  done
  ansible-lint ansible/ || FAILED=1
else
  echo "  ansible-lint not installed — pip install ansible-lint"
  FAILED=1
fi

# ---------------------------------------------------------------------------
# 2. Every Jinja expression lexes
#
# A template that cannot lex is a task that cannot run. ansible-lint does detect
# this class, but its failure mode is to CRASH -- the traceback replaces the
# report and every other finding in the run is lost. Six unrenderable templates
# hid behind one such crash, two of them in fact-gathering roles that had
# therefore never produced facts. This reports all of them at once instead.
# ---------------------------------------------------------------------------
hr; echo "2/7  jinja renderability"; hr
python3 scripts/check_jinja_renderable.py || FAILED=1

# ---------------------------------------------------------------------------
# 3. Playbook contracts
#
# Catches what lint cannot: a perfectly valid playbook that silently targets
# the wrong machine. See scripts/check_playbook_contracts.py.
# ---------------------------------------------------------------------------
hr; echo "3/7  playbook contracts"; hr
python3 scripts/check_playbook_contracts.py || FAILED=1

# ---------------------------------------------------------------------------
# 4. Role include targets exist
#
# Catches the class where a role's tasks/main.yml includes task files that
# were never written — three roles shipped broken this way for months.
# Syntax-check and YAML parsing both pass; the failure only appears when the
# include executes at runtime.
# ---------------------------------------------------------------------------
hr; echo "4/7  role include targets exist"; hr
if python3 "$REPO/scripts/check_role_include_targets.py"; then
  echo "  all role include targets resolve — OK"
else
  FAILED=1
fi

# ---------------------------------------------------------------------------
# 5. EDA template references resolve
#
# Rulebooks dispatch by AAP template NAME — a renamed or never-seeded
# template is a silent no-op. Exceptions are acknowledged with reasons in
# extensions/eda/rulebooks/known_unseeded.yml.
# ---------------------------------------------------------------------------
hr; echo "5/7  EDA template references resolve"; hr
python3 "$REPO/scripts/check_eda_template_refs.py" || FAILED=1

# ---------------------------------------------------------------------------
# 6. Fail-closed behaviour
#
# The patch playbooks must REFUSE when no target host is supplied rather than
# falling back to the controller. This asserts the refusal actually happens —
# we have twice been saved by environmental accident (the EE having no sudo, a
# template error) rather than by a control, and luck is not a control.
# ---------------------------------------------------------------------------
hr; echo "6/7  core/demos boundary"; hr
python3 "$REPO/scripts/check_core_demo_boundary.py" || FAILED=1

# ---------------------------------------------------------------------------
# 7. Fail-closed behaviour (see original comment above step 6)
# ---------------------------------------------------------------------------
hr; echo "7/7  fail-closed refusal"; hr
for pb in patch_backup patch_assurance patch_install; do
  printf '  %-20s ' "$pb"
  out="$(ansible-playbook "ansible/playbooks/${pb}.yml" -i localhost, 2>&1 || true)"
  # patch_install refuses via its own assert with different wording; accept either.
  if grep -qE "target_host is not set|target_host must be set" <<<"$out"; then
    echo "refuses without a target — OK"
  else
    echo "DID NOT REFUSE — a missing target must never fall through"
    FAILED=1
  fi
done

hr
if [ "$FAILED" -eq 0 ]; then
  echo "PASS — Ansible layer validated"
else
  echo "FAIL — see findings above"
fi
exit "$FAILED"
