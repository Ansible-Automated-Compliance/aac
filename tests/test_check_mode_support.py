"""Check mode contract for the playbooks that change managed hosts.

docs/reference/CHECK_MODE.md lists the playbooks that support `--check`.
For those, this pins the two things a preview depends on:

* a read-only command whose output later tasks read (`changed_when: false`
  plus `register`) runs under `--check` (`check_mode: false`); skipped, it
  leaves the later tasks with no data, and the crypto miner scan then
  reported a host with a miner on it as clean;
* no task that changes something opts out of check mode.
"""
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYBOOKS = ROOT / "ansible" / "playbooks"
DOC = ROOT / "docs" / "reference" / "CHECK_MODE.md"

SUPPORTED = [
    "apply_remediation.yml",
    "crypto_miner_detection_remediation.yml",
    "remediate_ocp_nerc_cip.yml",
    "hardening/windows_server_2022/harden_account_policies.yml",
    "hardening/windows_server_2022/harden_account_policies_fix.yml",
    "hardening/windows_server_2022/harden_audit_policy.yml",
    "hardening/windows_server_2022/harden_endpoint_security.yml",
    "hardening/windows_server_2022/harden_system_services.yml",
]

COMMAND = re.compile(r"(^|\.)(shell|command|raw|script|win_shell|win_command|win_powershell)$")

# Tasks allowed to run for real under --check although they write: each
# touches only a temporary file on the controller, never a managed host.
CONTROLLER_TEMP_FILE = {
    ("apply_remediation.yml", "Write generated tasks to temp file"),
    ("apply_remediation.yml", "Clean up temp task file"),
}


def _tasks(path):
    def walk(items):
        for task in items or []:
            if not isinstance(task, dict):
                continue
            for key in ("block", "rescue", "always"):
                yield from walk(task.get(key))
            yield task

    for play in yaml.safe_load(path.read_text()):
        for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
            yield from walk(play.get(key))


def _is_command(task):
    return any(COMMAND.search(key) for key in task)


@pytest.mark.parametrize("name", SUPPORTED)
def test_read_only_commands_with_consumers_run_in_check_mode(name):
    missing = [
        task.get("name")
        for task in _tasks(PLAYBOOKS / name)
        if _is_command(task)
        and task.get("changed_when") is False
        and "register" in task
        and task.get("check_mode") is not False
    ]
    assert not missing, f"{name}: read-only commands skipped under --check: {missing}"


@pytest.mark.parametrize("name", SUPPORTED)
def test_nothing_that_changes_a_host_opts_out_of_check_mode(name):
    opted_out = [
        task.get("name")
        for task in _tasks(PLAYBOOKS / name)
        if task.get("check_mode") is False
        and not (_is_command(task) and task.get("changed_when") is False)
        and (name, task.get("name")) not in CONTROLLER_TEMP_FILE
    ]
    assert not opted_out, f"{name}: tasks that run for real under --check: {opted_out}"


def test_document_lists_exactly_the_supported_playbooks():
    listed = set(re.findall(r"`ansible/playbooks/([\w/.-]+\.yml)`", DOC.read_text()))
    assert listed == set(SUPPORTED)
