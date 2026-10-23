# aac_oscap_scan

Runs `oscap xccdf eval` **on the target host** (read-only — never remediates,
never installs packages), fetches the XCCDF result XML to the execution
environment, and removes the result file from the target. Extracted from the
proven `ansible/playbooks/openscap_assess.yml` pipeline (#536); that playbook
now composes this role with `aac_oscap_ingest`.

An `oscap` exit code of 2 (scan completed, rules failed) is a **successful
assessment**; only a scanner error (rc 1) fails the run — otherwise a broken
scan could masquerade as "0 findings".

## Variables

| Variable | Criticality | Default | How to supply |
|---|---|---|---|
| `profile_id` | **CRITICAL — required, no default** | — | Survey or extra_vars. e.g. `xccdf_org.ssgproject.content_profile_stig`. A scan must never run against a profile the operator didn't choose |
| `datastream_path` | HIGH | `""` → auto-detected SSG path from the target's distro facts (e.g. `/usr/share/xml/scap/ssg/content/ssg-rhel9-ds.xml`) | extra_vars — point at a DISA-published or tailored datastream |
| `tailoring_path` | MEDIUM | `""` (none) | extra_vars — XCCDF tailoring file on the target |
| `oscap_target_tmpdir` | LOW | `/tmp` | extra_vars — target-side scratch for the (removed-after-fetch) result file |
| `oscap_fetch_dir` | LOW | `/tmp` | extra_vars — EE-side directory the result is fetched into |

## Outputs (facts for `aac_oscap_ingest`)

- `oscap_results_file` — EE-local XCCDF results path
- `oscap_version` — scanner version (for evidence metadata)
- `oscap_scan_rc` — raw oscap exit code (0 = all pass, 2 = findings)

## Requirements

Target needs `openscap-scanner` and a datastream (`scap-security-guide` for
SSG). This role deliberately does **not** install them — a package install is
a system change, and AAC assesses read-only. `become: true` required.
