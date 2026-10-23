# Customer Profiles

A **customer profile** declares one customer's environment in two
lists — `tech_stack` and `compliance_goals` — and
`derive_customer_frameworks.py` translates those into the framework
keys the OPA loader needs.

The point: stop shipping every customer the full 47-framework
policy library. Load only what their environment and obligations
actually require.

## How it fits together

```
customer profile YAML ────► derive_customer_frameworks.py
  (tech_stack +              │
   compliance_goals)         │  reads _tech_framework_map.yml
                             ▼
                       framework key set
                             │
                             ▼
                       load_opa_policies.yml
                       source=extra_vars
                       frameworks_to_load=<set>
                             │
                             ▼
                       OPA containers loaded with
                       only the customer's policies
```

The customer never sees the framework keys. They're a translation
layer. The customer says "we run RHEL 9 on AWS, we have to comply
with PCI-DSS"; the rest is derivation.

## File layout

```
customer_profiles/
├── README.md                       ← this file
├── _template.yml                   ← copy to start a new profile
├── _tech_framework_map.yml         ← tech / compliance → keys mapping
├── demos/                          ← per-demo profiles for validation
│   ├── comply.yml
│   ├── golden_image.yml
│   └── …
└── examples/                       ← example real-customer profiles
    └── acme_energy.yml
```

## Adding a new customer

```bash
cp customer_profiles/_template.yml customer_profiles/examples/foo.yml
$EDITOR customer_profiles/examples/foo.yml
# Fill in tech_stack + compliance_goals.

scripts/derive_customer_frameworks.py \
    customer_profiles/examples/foo.yml \
    --format=ansible
# → comma-separated framework keys

# Drop those into the load playbook:
ansible-playbook ansible/playbooks/load_opa_policies.yml \
    -e source=extra_vars \
    -e "frameworks_to_load=cis_benchmarks,nist_800_53,iso27001,pci_dss"
```

`--format=yaml` prints a derivation trace — useful when a key
turns up that the customer didn't expect.

## Adding a new tech or compliance goal

Edit `_tech_framework_map.yml`. The two tables there are the only
place the mapping lives — every profile and every demo references
keys from this file. If a customer asks for "OpenStack Ironic" and
that tech isn't in the table, the derivation script fails loudly
(exit 2) rather than silently dropping it.

The framework keys themselves come from
`ansible/playbooks/load_opa_policies.yml` — that's the source of
truth for "what the loader understands."

## Per-demo profiles

Every AAC demo we maintain has a profile in `demos/`. The intent:

- Document what each demo actually needs from OPA (much less than
  the full library)
- Provide test fixtures for `validate_demo_bundle.py` (TODO — next
  PR) which spins up a fresh OPA container, loads the demo's
  derived bundle, runs the demo's playbooks, and confirms the
  expected results still come back

When a new demo lands, add its profile here. Each profile's
`demo_validations` block lists the OPA URLs the demo actually
queries — keep that list current.

## When the derivation is wrong

Three escape hatches, in increasing severity:

1. **`overrides.add`** — force-load a framework that derivation
   doesn't pick up. Use when a customer's environment has a
   genuine edge case (e.g. they run RHEL 9 but only care about
   PCI-DSS subset, AND they want NIST 800-82 because their parent
   org demands it).
2. **`overrides.remove`** — force-exclude a derived framework.
   Use when derivation pulls in a transitive dependency the
   customer explicitly doesn't want (e.g. compliance_goals=`soc2`
   pulls `iso27001` by default; some customers want SOC 2 only
   and treat ISO mappings as out of scope).
3. **Edit `_tech_framework_map.yml`** — the right fix when the
   mapping itself is wrong. Don't paper over a mapping bug with
   per-profile overrides; the next customer with the same tech
   gets the same bug.

## Validation

The PR that landed this file did not yet ship
`validate_demo_bundle.py`. That's the next deliverable on this
thread. The intended workflow:

```bash
scripts/validate_demo_bundle.py customer_profiles/demos/comply.yml
# 1. Derives the framework key set
# 2. Spins up a throwaway OPA container
# 3. Runs the loader against it with extra_vars=<derived set>
# 4. Hits every demo_validations.opa_url and checks expected_keys
# 5. Reports bundle size + count of Rego files loaded
```

Until that lands, validation is manual — derive the keys, load
into a test OPA, run the demo playbooks, eyeball.

## Running the tests

```bash
pip install -r scripts/requirements.txt   # pytest is in there
pytest scripts/test_derive_customer_frameworks.py -v
```

The tests pin:

- Tech / compliance contributions accumulate (union).
- `overrides.add` / `overrides.remove` behave as documented.
- Unknown tech / compliance / framework keys exit non-zero
  (fail loud, never silently drop coverage).
- Every shipped profile under `demos/` and `examples/` derives a
  non-empty set the OPA loader can consume.
