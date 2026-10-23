# AAC consumer bridges

Alias modules that map **AAC's `opa_framework_map` keys** to the policy
library's **canonical entrypoints**.

These are AAC's files, not the library's, and that is the point.

## Why they live here

`ynotbhatc/rego_policy_libraries` is a standalone library. It ships Apache-2.0
with a public OCI bundle and is meant to be consumable by anyone running OPA or
EOPA, with no knowledge of AAC. So it names each framework's entrypoint after
the package that actually holds the policy:

    cis_ubuntu_22_04.main.compliance_report
    stig.kubernetes.main.compliance_report
    nist.sp800_53.main.compliance_report

AAC addresses frameworks by its own keys, which are spelled differently:

    cis_ubuntu_2204        stig_kubernetes        nist_800_53

Translating between the two is **AAC's concern**, not the library's. Putting
these aliases in the library would push AAC's vocabulary into an artifact other
people consume. They belong here.

## What stays in the library

The normalized `<package>.main.compliance_report` entrypoint and the
fail-closed gate stay upstream. "Give me framework X's compliance report" is
useful to any consumer, and refusing to report a pass when no facts were
supplied is a safety property no consumer should have to reimplement.

Only the **vocabulary** lives here.

## Current bridges

| AAC key | canonical library entrypoint | bucket |
|---|---|---|
| `cis_ubuntu_2004` | `cis_ubuntu_20_04.main` | security |
| `cis_ubuntu_2204` | `cis_ubuntu_22_04.main` | security |
| `cis_ubuntu_2404` | `cis_ubuntu_24_04.main` | security |
| `cis_windows_2019` | `cis_windows_server_2019.main` | security |
| `cis_windows_2022` | `cis_windows_server_2022.main` | security |
| `cis_rhel10` | `cis.rhel_10.main` | security |
| `stig_kubernetes` | `stig.kubernetes.main` | security |
| `stig_openshift_4` | `stig.openshift_4.main` | security |
| `stig_rke2` | `stig.rke2.main` | security |
| `nist_800_53` | `nist.sp800_53.main` | security |
| `nist_csf` | `nist.csf.main` | security |
| `nist_ai_rmf` | `nist.ai_rmf.main` | ot |

Every other key in `opa_framework_map` addresses a library package whose name
already matches, and needs no bridge.

## Layout

One directory per OPA container, named for the bucket in `opa_framework_map`:

    opa_bridges/security/   -> opa-security
    opa_bridges/compliance/ -> opa-compliance
    opa_bridges/ot/         -> opa-ot

`ansible/playbooks/load_opa_policies.yml` loads these **after** the library, so
the canonical entrypoint each alias points at is already in the container. They
are PUT with an `aac_bridge_` policy-ID prefix so they never collide with a
library policy.

Unlike the library load, a bridge that fails to load is a **hard failure**. A
missing bridge means its framework key returns `{}` and every assessment for
that framework fails — better to stop the play than to discover it per-job.

## Adding a bridge

1. Drop `opa_bridges/<bucket>/<aac_key>.rego` using an existing file as a
   template.
2. `package <aac_key>.main`, then
   `compliance_report := data.<canonical>.main.compliance_report`.
3. **Do not add a `default`.** If the library entrypoint is missing — bad
   submodule pin, partially loaded container — the rule must be undefined so
   OPA returns `{}` and `generic_framework_assessment.yml` fails the job.
   Defaulting turns a loud failure into a silently empty result, which is the
   exact bug class the fail-closed work was undoing.
4. Confirm the key exists in `opa_framework_map` in
   `ansible/vars/site_config.yml` and is in the matching bucket.

## Verifying

Evaluate the library plus these bridges together and confirm each AAC key
resolves to a populated, fail-closed report on empty input:

```bash
opa eval -d policies -d opa_bridges/security \
  -f pretty 'data.cis_ubuntu_2204.main.compliance_report'
```

Expect a populated object with `compliant: false` — never `{}`, never a pass.
