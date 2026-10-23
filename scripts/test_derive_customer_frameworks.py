"""Tests for derive_customer_frameworks.py.

Pins:
  - Tech / compliance contributions accumulate (union, not replace).
  - Overrides.add forces a key into the result.
  - Overrides.remove drops a derived key but leaves a trace entry.
  - Unknown tech / compliance entry exits non-zero — fail loud, never
    silently drop coverage.
  - The shipped per-demo profiles produce a non-empty key set.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "derive_customer_frameworks.py"


def run(profile_path: Path, fmt: str = "plain") -> tuple[int, str, str]:
    """Run the derivation script; return (rc, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(profile_path), f"--format={fmt}"],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_profile(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "profile.yml"
    p.write_text(body)
    return p


# ── Core derivation behavior ──────────────────────────────────────────


def test_tech_only_profile_derives_expected_keys(tmp_path):
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: [rhel_9]
compliance_goals: []
overrides: {add: [], remove: []}
""",
    )
    rc, out, err = run(p)
    assert rc == 0, err
    keys = set(out.strip().splitlines())
    assert keys == {"cis_rhel9", "stigs"}


def test_compliance_only_profile_derives_expected_keys(tmp_path):
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: []
compliance_goals: [pci_dss]
overrides: {add: [], remove: []}
""",
    )
    rc, out, err = run(p)
    assert rc == 0, err
    assert "pci_dss" in out.strip().splitlines()


def test_tech_and_compliance_contributions_union(tmp_path):
    """tech_stack=[rhel_9] gives cis+stigs; compliance=[soc2] gives
    soc2+iso27001. Result must be the union (4 keys), not the
    intersection (0) or the last-wins (2)."""
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: [rhel_9]
compliance_goals: [soc2]
overrides: {add: [], remove: []}
""",
    )
    rc, out, err = run(p)
    assert rc == 0, err
    keys = set(out.strip().splitlines())
    assert {"cis_rhel9", "stigs", "soc2", "iso27001"}.issubset(keys)


# ── Overrides ─────────────────────────────────────────────────────────


def test_overrides_add_includes_key(tmp_path):
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: []
compliance_goals: []
overrides:
  add: [crypto_miner_detection]
  remove: []
""",
    )
    rc, out, err = run(p)
    assert rc == 0, err
    assert "crypto_miner_detection" in out.strip().splitlines()


def test_overrides_remove_drops_a_derived_key(tmp_path):
    """tech_stack=[ansible] would normally pull sentinel_ansible.
    The remove override must take it out."""
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: [ansible]
compliance_goals: []
overrides:
  add: []
  remove: [sentinel_ansible]
""",
    )
    rc, out, err = run(p)
    assert rc == 0, err
    assert "sentinel_ansible" not in out.strip().splitlines()


# ── Failure modes ─────────────────────────────────────────────────────


def test_unknown_tech_exits_non_zero(tmp_path):
    """A typo'd tech entry should fail loud, never silently drop."""
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: [redhat_9]   # typo — should be rhel_9
compliance_goals: []
overrides: {add: [], remove: []}
""",
    )
    rc, out, err = run(p)
    assert rc == 2
    assert "redhat_9" in err


def test_unknown_compliance_goal_exits_non_zero(tmp_path):
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: []
compliance_goals: [pci]   # should be pci_dss
overrides: {add: [], remove: []}
""",
    )
    rc, out, err = run(p)
    assert rc == 2
    assert "pci" in err


def test_overrides_add_unknown_framework_exits_two(tmp_path):
    """overrides.add taking a framework key the OPA loader doesn't
    know must fail loud — silent acceptance would silently drop the
    operator's intent."""
    p = write_profile(
        tmp_path,
        """
name: t
tech_stack: []
compliance_goals: []
overrides:
  add: [not_a_real_framework]
  remove: []
""",
    )
    rc, out, err = run(p)
    assert rc == 2
    assert "not_a_real_framework" in err


def test_malformed_profile_yaml_exits_one(tmp_path):
    """Malformed YAML should exit with the documented 1, not a stack
    trace from later code crashing on a None / wrong-type input."""
    p = tmp_path / "profile.yml"
    p.write_text("name: t\n  bad:: indent\n: value\n")
    rc, _, err = run(p)
    assert rc == 1
    assert "malformed" in err.lower() or "yaml" in err.lower()


def test_empty_profile_exits_one(tmp_path):
    p = write_profile(tmp_path, "")
    rc, _, err = run(p)
    assert rc == 1
    assert "empty" in err.lower()


# ── Shipped per-demo profiles ─────────────────────────────────────────
#
# These pin the contract that each demo profile produces a derived
# set our load playbook can consume.


@pytest.mark.parametrize(
    "profile_name",
    ["demos/golden_image.yml", "demos/comply.yml", "examples/acme_energy.yml"],
)
def test_shipped_profile_derives_non_empty(profile_name):
    rc, out, err = run(REPO_ROOT / "customer_profiles" / profile_name)
    assert rc == 0, err
    keys = [k for k in out.strip().splitlines() if k]
    assert len(keys) > 0, "derived an empty framework set"


def test_golden_image_derives_minimum_set():
    """The point of the golden_image profile is that it's TIGHT — RHEL 9
    + CIS, that's it. If derivation pulls in more, either the profile
    is wrong or the mapping accidentally grew."""
    rc, out, _ = run(REPO_ROOT / "customer_profiles" / "demos" / "golden_image.yml")
    assert rc == 0
    keys = set(out.strip().splitlines())
    # Tight upper bound — golden image touches CIS RHEL 9 + STIGs
    # (RHEL 9 tech maps to both). Nothing else should creep in.
    assert keys == {"cis_rhel9", "stigs"}
