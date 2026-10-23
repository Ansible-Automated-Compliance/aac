# CIS pfSense collector payload harness

Runs the payload tasks of `ansible/playbooks/cis_pfsense_assessment.yml` (from
"Read pfsense_attest" to "Add message of the day text") with Ansible's own
templating engine, evaluating each task's real `when:` and `loop:`, against a
fixture device. No hosts, no AAP job.

```bash
PY=$(head -1 "$(command -v ansible-playbook)" | sed 's/^#!//')   # the interpreter that has ansible
$PY tests/pfsense_collector/render_payload.py
# optionally score the payloads against a policy directory:
$PY tests/pfsense_collector/render_payload.py --opa "$(command -v opa)" \
    --policy policies/benchmarks/cis/network_devices/pfsense --show-violations
```

The assertions hold at any library pin: every section the CIS pfSense Firewall
v1.1.1 policy reads (`syslog`, `hasync`, `openvpn`, `sshd_config`, `motd`,
`attest`) is sent when the device has it and the v1.0.0 keys stay; a section or
file the device lacks or that could not be read is not sent (no empty object, no
empty OpenVPN server list), so the policy reports evidence missing; `attest`
defaults to `{}` and survey strings become real booleans; hostile device
strings are carried verbatim and never templated.

Fixtures (synthetic, RFC 5737 addresses, example.com):

- `fixtures/pfsense_hardened.fixture.json`: a pfSense device in the shape a
  parsed `config.xml` takes (a single repeated element as an object, checkbox
  flags as `""` or `{}`, `<any/>` as `{}`), plus its `sshd_config` and `motd`.
- `fixtures/sim_device_files.fixture.json`: what the demo sim container
  (`deploy_pfsense_aws.yml`) returns for `sshd_config` and `motd`. The sim's
  config document itself is read from `deploy_pfsense_aws.yml`.

Scores at the library commit carrying CIS pfSense v1.1.1 (rego `001dbe08`,
2026-10-21):

| Case | attest `{}` | all 7 attested |
|---|---|---|
| hardened fixture | 78.8% (26/33) | 100% (33/33) |
| demo sim | 36.4% (12/33) | 57.6% (19/33) |

At the current pin (v1.0.0 policy) the demo sim still scores 87.5%: the new keys
are additive.
