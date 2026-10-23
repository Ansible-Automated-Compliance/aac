# PQC mapper unit harness

Renders `ansible/tasks/pqc_build_opa_input.yml` with Ansible's own templating
engine (no playbook run, no hosts) against a fixture in the shape
`collect_pqc_crypto_facts.yml` produces, then evaluates the result against the
Rego library's `frameworks/federal/pqc`. This is how "the playbook really sends
what the policy reads" is proven without an AAP job — the same method as
`tests/stig_mapper/` and `tests/cis_mapper/`.

```bash
PY=$(head -1 "$(command -v ansible-playbook)" | sed 's/^#!//')   # the interpreter that has ansible
$PY tests/pqc_mapper/render_pqc_mapper.py tests/pqc_mapper/fixture_pqc_raw.json /tmp/pqc_input.json
opa eval -f pretty -d policies/frameworks/federal/pqc -i /tmp/pqc_input.json 'data.pqc.main.compliance_report'
```

Expected with the shipped fixture (2026-10-21, library at the pinned commit):
profile `federal`, 14 controls evaluated, 17 inventory rows, 3 PQC assets
(the ML-DSA-65 certificate, the `mlkem768x25519` key exchange and the
`X25519MLKEM768` TLS group count under the policy's markers), 10
quantum-vulnerable assets, and 9 violations: the six unplanned vulnerable
algorithms (the RSA-1024 legacy CA, the ECDSA certificate, the three SSH host
keys, the `X25519` TLS listener), the broken SHA-1 hash, and the two
attestations left false (`hndl_data_identified`, `contractor_fips_pqc_required`).
The RSA server certificate and sshd's vulnerable key-exchange entries are
listed in `pqc_migration_planned_assets` and are therefore not violations. The
unparsable certificate produces no row; it appears in
`system_info.collector_notes`. The `sntrup761x25519` key exchange is neither
vulnerable nor a FIPS PQC algorithm and is counted as neither.

The fixture is synthetic (no lab identifiers, no secrets, no key material).
The harness also proves a hostile payload (`{{ lookup('pipe','id') }}`) placed
in a certificate path, a key-exchange name and a TLS group survives verbatim
and nothing is evaluated.
