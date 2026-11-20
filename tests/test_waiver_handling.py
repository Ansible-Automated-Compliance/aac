"""Waiver handling in the loader and the results role.

Static checks on the task files: the behaviour itself is exercised against a
live OPA in the pull request that added these tasks.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "ansible/roles/aac_store_results/tasks/main.yml"
LOADER = ROOT / "ansible/playbooks/load_opa_policies.yml"


def _names(tasks):
    return [t.get("name", "") for t in tasks]


def test_waiver_outcome_is_cleared_before_each_query():
    """A second result for the same host must not inherit the first one's
    waived violations and metadata."""
    tasks = yaml.safe_load(ROLE.read_text())
    names = _names(tasks)
    clear = names.index("Clear the waiver outcome of any earlier call for this host")
    query = names.index("Query waiver decision from OPA")
    assert clear < query
    facts = tasks[clear]["set_fact"]
    assert set(facts) == {"_aac_violations_final", "_aac_metadata_final", "_aac_waived_count"}
    assert "when" not in tasks[clear], "the reset must run on every call"


def test_refused_and_expiring_waivers_are_stored():
    text = ROLE.read_text()
    for key in ("waivers_refused", "waivers_refused_count", "waivers_expiring_soon"):
        assert key in text


def test_loader_pushes_entries_and_settings():
    play = yaml.safe_load(LOADER.read_text())[0]
    push = next(t for t in play["tasks"] if t.get("name") == "Push waiver entries as OPA data")
    body = push["uri"]["body"]
    assert set(body) == {"entries", "settings"}


def test_shipped_waiver_file_has_no_rules_and_the_example_parses():
    shipped = yaml.safe_load((ROOT / "ansible/vars/waivers.yml").read_text())
    assert shipped == {"waiver_entries": [], "waiver_settings": {}}
    example = yaml.safe_load((ROOT / "examples/waivers_example.yml").read_text())
    required = example["waiver_settings"]["required_fields"]
    for entry in example["waiver_entries"]:
        for field in required + ["host", "framework", "control_id", "expires"]:
            assert str(entry.get(field, "")).strip(), f"{entry['control_id']} lacks {field}"
