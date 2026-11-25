"""The collector catalog lists what is in the tree, and the README table matches it."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("collector_catalog", ROOT / "scripts" / "collector_catalog.py")
cc = importlib.util.module_from_spec(spec)
sys.modules["collector_catalog"] = cc
spec.loader.exec_module(cc)


def test_catalog_has_no_problems():
    assert cc.problems(cc.load()) == []


def test_readme_table_is_current():
    text = cc.README.read_text()
    assert cc.rendered(cc.load(), text) == text, "run: python3 scripts/collector_catalog.py --write"


def test_every_collector_states_how_and_where():
    for entry in cc.load()["collectors"]:
        assert entry["how"].endswith("."), entry["id"]
        assert entry["paths"], entry["id"]


def _tree(tmp_path, files):
    for rel in files:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\n")
    return tmp_path


def _entry(**changes):
    entry = {
        "id": "linux", "target": "Linux hosts", "source": "in_repo", "how": "Facts.", "reach": "SSH",
        "uses": ["ansible.builtin.setup"], "paths": ["ansible/playbooks/cis_x_assessment.yml"],
        "stores": "none", "feeds": "A policy",
    }
    entry.update(changes)
    return entry


def test_unlisted_collector_file_is_reported(tmp_path):
    root = _tree(tmp_path, ["ansible/playbooks/cis_x_assessment.yml", "ansible/tasks/collect_new_facts.yml"])
    found = cc.problems({"collectors": [_entry()]}, root)
    assert found == [
        "not in the catalog: ansible/tasks/collect_new_facts.yml (add it to a collector, or to not_collectors with a reason)"
    ]


def test_not_collectors_needs_a_reason_and_clears_the_file(tmp_path):
    root = _tree(tmp_path, ["ansible/playbooks/cis_x_assessment.yml", "ansible/playbooks/export_assessment.yml"])
    listed = {"collectors": [_entry()], "not_collectors": [{"path": "ansible/playbooks/export_assessment.yml", "reason": "Exports."}]}
    assert cc.problems(listed, root) == []
    listed["not_collectors"][0]["reason"] = ""
    assert any("has no reason" in line for line in cc.problems(listed, root))


def test_missing_path_duplicate_and_bad_source_are_reported(tmp_path):
    root = _tree(tmp_path, ["ansible/playbooks/cis_x_assessment.yml"])
    catalog = {"collectors": [_entry(), _entry(paths=["ansible/playbooks/gone.yml"]), _entry(id="other", source="magic")]}
    found = "\n".join(cc.problems(catalog, root))
    assert "path does not exist: ansible/playbooks/gone.yml" in found
    assert "linux: listed twice" in found
    assert "other: source must be one of" in found


def test_a_directory_path_covers_the_files_under_it(tmp_path):
    root = _tree(tmp_path, ["ansible/roles/aac_facts_collector/tasks/linux_ssh.yml"])
    assert cc.problems({"collectors": [_entry(paths=["ansible/roles/aac_facts_collector"])]}, root) == []
