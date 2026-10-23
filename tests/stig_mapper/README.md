# STIG mapper unit harness

Renders `ansible/tasks/stig_linux_build_opa_input.yml` and
`ansible/tasks/oracle_db_build_opa_input.yml` with Ansible's own templating
engine (no playbook run, no hosts) against a fixture in the shape the
collectors produce, then evaluates the result against the Rego library. This is
how "the playbook really sends what the policy reads" is proven without an AAP
job — the same method as `tests/cis_mapper/`.

```bash
PY=$(head -1 "$(command -v ansible-playbook)" | sed 's/^#!//')   # the interpreter that has ansible

# Linux (RHEL 8/9, Oracle Linux 8/9 share one contract)
$PY tests/stig_mapper/render_stig_mapper.py ansible/tasks/stig_linux_build_opa_input.yml \
    tests/stig_mapper/fixture_ol9_facts.json /tmp/stig_input.json
for p in oracle_linux_9 rhel_9 oracle_linux_8 rhel_8; do
  opa eval -f raw -d policies/benchmarks/stig/$p -i /tmp/stig_input.json \
    "sprintf(\"$p %d/%d\", [data.stig.$p.main.compliance_report.passed_controls, data.stig.$p.main.compliance_report.total_controls])"
done

# Oracle Database 19c
$PY tests/stig_mapper/render_stig_mapper.py ansible/tasks/oracle_db_build_opa_input.yml \
    tests/stig_mapper/fixture_oracle19c_raw.json /tmp/ora_input.json
opa eval -f pretty -d policies/benchmarks/stig/oracle_database_19c -i /tmp/ora_input.json \
    'object.remove(data.stig.oracle_database_19c.main.compliance_report, {"open_findings"})'
```

Expected with the shipped fixtures (2026-10-13): the Oracle Linux 9 fixture
scores 92/93 (the one Open is IPv6 not disabled, a real finding in the
fixture), RHEL 9 140/143, Oracle Linux 8 67/68, RHEL 8 71/73; the 19c fixture scores 43/96 (every attestation Open until
`oracle_stig_attestations` is supplied, plus the fixture's database link, admin
role, owner, component, option and patch until they are allowlisted) and 96/96
on the green path.
Both fixtures are synthetic (RFC 5737 addresses, no lab identifiers, no
secrets). The harness also proves a hostile payload (`{{ lookup('pipe','id') }}`)
placed in a banner, an sshd value, a sysctl value or the instance name survives
verbatim and nothing is evaluated.
