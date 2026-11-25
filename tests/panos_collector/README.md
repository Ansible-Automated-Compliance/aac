# PAN-OS CIS collector: scoring harness

`score_fixture.py` runs PAN-OS running configurations through the mapper
(`collections/ansible_collections/aac/panos/plugins/filter/panos_cis_facts.py`)
and then through the CIS Palo Alto policy itself, and asserts the verdicts.

```bash
python3 tests/panos_collector/score_fixture.py --opa "$(command -v opa)" \
  --policy policies/benchmarks/cis/network_devices/palo_alto
```

It needs an `opa` binary and the policy directory, so it is not a pytest test.
The mapper's own unit tests (no `opa`, no policy) are in
`collections/ansible_collections/aac/panos/tests/unit/` and run with the rest of
the suite.

To see what a configuration you have exported would score (no site
classification, no attestations, no licenses):

```bash
python3 tests/panos_collector/score_fixture.py --config my_running_config.xml
```
