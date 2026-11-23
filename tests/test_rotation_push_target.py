"""The credential-rotation playbook must never push the vault to the public
upstream repository, and must not carry the token in a URL."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "ansible/playbooks/rotation_update_vault.yml"
EDA = ROOT / "ansible/playbooks/setup_eda_drift_detection.yml"


def _play():
    return yaml.safe_load(PLAYBOOK.read_text())[0]


def test_no_repository_url_is_written_into_the_playbook():
    text = PLAYBOOK.read_text()
    assert "github.com/" not in text.replace("github\\\\.com", "")
    assert "projects/11/" not in text


def test_guard_runs_first_and_names_the_public_upstream():
    tasks = _play()["tasks"]
    guard = tasks[0]
    assert guard["name"].startswith("Refuse to push the vault")
    rules = " ".join(guard["ansible.builtin.assert"]["that"])
    assert "ansible-automated-compliance/aac" in rules
    assert "YOUR_ORG" in rules
    assert "when" not in guard


def test_token_is_not_in_the_push_command():
    push = next(t for t in _play()["tasks"] if t.get("name") == "Commit updated vault to git")
    assert "vault_github_pat" not in push["shell"]
    assert "vault_github_pat" in push["environment"]["GIT_CONFIG_VALUE_0"]
    assert push["no_log"] is True


def test_eda_project_url_follows_the_site_repository():
    play = yaml.safe_load(EDA.read_text())[0]
    assert "git_repo_url" in play["vars"]["eda_project_url"]
    create = next(t for t in play["tasks"] if t.get("name") == "Create EDA Project")
    assert create["ansible.builtin.uri"]["body"]["url"] == "{{ eda_project_url }}"
