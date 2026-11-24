# Check mode (`--check`)

Check mode is supported for the playbooks that change managed hosts. Assessment playbooks only read facts and store results, so a preview adds nothing there; they are not written for check mode and should be run normally.

## Supported playbooks

| Playbook | What `--check` does |
|---|---|
| `ansible/playbooks/apply_remediation.yml` | With `dry_run=false`, runs the generated remediation tasks in check mode: each reports what it would change on the host. Nothing is changed, and no audit record or status update is written. With `dry_run=true` (the default) it prints the plan as before. |
| `ansible/playbooks/crypto_miner_detection_remediation.yml` | Runs the full detection scan and reports findings. With `auto_remediate=true`, package, service and file removals report what they would do; processes are not killed. The play ends failed when a miner is found, because nothing was removed. |
| `ansible/playbooks/remediate_ocp_nerc_cip.yml` | Reads the pending remediations and, with `apply_remediations=true`, sends each patch as a dry run. The result metadata is labelled `check mode (nothing applied)`. |
| `ansible/playbooks/hardening/windows_server_2022/harden_account_policies.yml` | Registry, service and user-right tasks report what they would change. Tasks that run a Windows command are skipped (see limits). |
| `ansible/playbooks/hardening/windows_server_2022/harden_account_policies_fix.yml` | As above. |
| `ansible/playbooks/hardening/windows_server_2022/harden_audit_policy.yml` | As above; the current audit policy is still read. |
| `ansible/playbooks/hardening/windows_server_2022/harden_endpoint_security.yml` | As above. |
| `ansible/playbooks/hardening/windows_server_2022/harden_system_services.yml` | As above. |

In AAP, set **Job type: Check** on the job template, or enable "Prompt on launch" for the job type.

## Limits

- A task that runs a command (`shell`, `command`, `win_shell`) cannot say what it would change, so Ansible skips it under `--check`. The Windows hardening playbooks set password, lockout, audit, Defender and firewall policy with `secedit`, `auditpol`, `net accounts` and `Set-MpPreference`; those settings are not previewed. Each playbook prints how many of its tasks are skipped for this reason.
- Read-only commands whose output later tasks depend on are marked `check_mode: false` and run under `--check`. They change nothing.
- `apply_remediation.yml` writes and removes one temporary task file on the controller under `--check`. No managed host is touched.

## How this is kept true

`tests/test_check_mode_support.py` fails when a supported playbook gains a read-only command that later tasks read but that would be skipped under `--check`, when a task that changes a host opts out of check mode, or when this list and the test's list differ.

`crypto_miner_detection_remediation.yml` was run under `--check` on RHEL 9 with a miner-named file planted: the scan reported it, the removal was previewed, and the file was still present afterwards. Before this change the same run skipped the whole scan and reported the host clean. The Windows and OpenShift playbooks have not been run under `--check` against a live host.
