# HashiCorp Vault Enterprise

## At a glance

- **Customer system:** HashiCorp Vault Enterprise (HVE) — centralized secrets-management platform
- **AAP pattern:** pull from external system (AAP reads at runtime)
- **Status:** ⚠ partial — customer already has AWX↔Vault Credential Plugin working; AAP playbooks have no `community.hashi_vault` lookups yet
- **Effort estimate:** 3–5 person-days for a competent AAP engineer (most time is policy / role / namespace mapping with the customer's Vault admin team)
- **Required collections:**
  - `community.hashi_vault` v7.1.0 (Galaxy + Automation Hub certified) — for playbook-runtime lookups
  - AAP Credential Plugin (built into AAP — no collection needed) — for AAP-managed credentials
- **Customer-side prerequisites:**
  - Vault Enterprise license (some features used by AAP require the Enterprise tier — namespaces, performance replication, audit-log streaming)
  - Vault auth method for AAP service identity. **Recommended:** AppRole with role_id known and secret_id rotated regularly. Alternatives: JWT/OIDC (best when AAP runs in OCP and pod identities are projected as JWTs), Token (dev/lab only).
  - Pre-created Vault paths the AAP service identity can read (e.g. `secret/aap/<env>/...`)
  - Vault policy granting `read` (not `create` or `update`) on those paths
  - For HVE namespaces: customer's chosen namespace path for AAP (e.g. `aap/prod`)

## Customer use case

The customer's policy bars plaintext secrets in any system. Their existing
AWX install already reads credentials from Vault via the AAP Credential
Plugin. Two things move when they migrate to AAP 2.6 plus net-new
automation:

1. **AAP-managed credentials** (Machine, Cloud, Source Control) need to
   keep working — the same credential bindings carry forward from AWX
   into AAP 2.6 with zero code change as long as the URL of the Vault
   instance is unchanged.
2. **Playbook-runtime secrets** (anything more granular than a small
   set of named credentials — per-environment API keys, certificates,
   short-lived database passwords) need to land in playbooks via
   `community.hashi_vault` lookups at the moment a task runs, never
   stored on disk.

This integration covers both surfaces and gives the customer's policy
team an audit trail in Vault for every secret AAP reads.

## Architecture / data flow

```
   ┌──────────────────────┐                    ┌──────────────────────────┐
   │ AAP Controller       │                    │ Vault Enterprise         │
   │                      │                    │ https://vault.acme.com   │
   │ Credentials:         │ ── lookup ───────► │                          │
   │  - Machine: linux    │   (AppRole auth,    │ Auth backends:           │
   │  - Cloud: aws-prod   │    runtime fetch)   │  - approle/aap           │
   │  - SCM: github       │                    │  - jwt/aap-ocp           │
   └──────────────────────┘                    │                          │
                                               │ KV v2 secrets:           │
   ┌──────────────────────┐                    │  - secret/aap/prod/…     │
   │ AAP playbook tasks   │                    │  - secret/aap/dev/…      │
   │ (`uri`, `community.  │ ── community.      │                          │
   │  postgresql`, etc.)  │    hashi_vault     │ Audit log:               │
   │                      │    lookup ───────► │  - file / syslog / SIEM  │
   └──────────────────────┘                    │  - records every read    │
                                               └──────────────────────────┘
                                                              │
                                                              ▼
                                                  ┌──────────────────────┐
                                                  │ Customer's SIEM      │
                                                  │ (Vault audit log     │
                                                  │  forwarded for       │
                                                  │  compliance review)  │
                                                  └──────────────────────┘
```

The AAP host never writes to Vault — strict read-only role. Secrets
never land on the AAP filesystem (the lookup result lives in process
memory during the task and is GC'd after).

## Required collections

| Collection | Vendor | Availability | In our EE? | Version | Used for |
|---|---|---|---|---|---|
| `community.hashi_vault` | Community (certified by Red Hat in Automation Hub) | Galaxy + Automation Hub | no (add via EE rebuild) | 7.1.0 | `vault_kv2_get`, `vault_read`, `vault_login`, `vault_token_create` lookup plugins for runtime secret resolution |
| AAP Credential Plugin (HashiCorp Vault Secret Lookup) | Red Hat (bundled with AAP) | bundled | yes | bundled | UI-driven binding of AAP credential fields to Vault paths (no Ansible code) |

## Integration steps

### Step 1 — Confirm the Vault auth backend + policy for the AAP service identity

1. **What:** AAP needs an identity Vault recognizes that can read the AAP secrets paths
2. **How:**
   - Customer's Vault admin enables the AppRole auth backend at `auth/approle/`
   - Creates a Vault policy named `aap-read`:
     ```hcl
     path "secret/data/aap/*" {
       capabilities = ["read", "list"]
     }
     path "secret/metadata/aap/*" {
       capabilities = ["read", "list"]
     }
     ```
   - Creates a role `aap` bound to the policy:
     ```bash
     vault write auth/approle/role/aap \
       token_policies="aap-read" \
       token_ttl=1h token_max_ttl=4h \
       secret_id_ttl=24h secret_id_num_uses=0
     ```
   - Hands the resulting `role_id` (non-secret) and `secret_id` (secret) to the AAP admin
3. **Verify:** From the AAP host:
   ```bash
   curl --request POST \
     --data '{"role_id":"<role_id>","secret_id":"<secret_id>"}' \
     https://vault.acme.com:8200/v1/auth/approle/login \
     | jq -r .auth.client_token
   ```
   should return a non-empty token. Then:
   ```bash
   curl -H "X-Vault-Token: <token>" \
     https://vault.acme.com:8200/v1/secret/data/aap/prod/healthcheck
   ```
   should return 200 (path may be empty — that's fine; 404 is also fine; 403 means the policy is wrong)

### Step 2 — Store the AAP service identity locally

1. **What:** The `role_id` + `secret_id` need to be reachable by AAP playbooks; classic chicken-and-egg
2. **How:**
   - Option A (simplest, lowest-secrecy ask) — store in `ansible/vars/site_config.yml` (gitignored on this repo) with file mode 0600
   - Option B (better) — bind environment variables `VAULT_ROLE_ID` + `VAULT_SECRET_ID` into the EE at AAP launch via a Custom Credential type
   - Option C (best, but adds setup) — short-lived JWT bootstrap from an external identity (cloud-init metadata, OCP service-account-token projection); AAP exchanges the JWT for a Vault token at launch time, no static role_id needed
3. **Verify:** A trivial playbook can lookup a known path:
   ```yaml
   - name: Vault smoke test
     debug:
       msg: "{{ lookup('community.hashi_vault.vault_kv2_get', 'aap/prod/healthcheck',
                       url=vault_addr, auth_method='approle',
                       role_id=lookup('env','VAULT_ROLE_ID'),
                       secret_id=lookup('env','VAULT_SECRET_ID')).data.value }}"
   ```
   returns the expected string (or `none` if the path is empty — the lookup mechanics work either way)

### Step 3 — Migrate AAP's named credentials to use the Credential Plugin

1. **What:** Re-bind every AAP credential whose plaintext secret should live in Vault
2. **How (per credential, UI-only — no playbook code):**
   - AAP UI → **Settings → Credentials → \<credential> → Edit**
   - For the secret field (Password, SSH Private Key, AWS Secret Key, GitHub PAT, etc.) click the **External Secret** key icon
   - Pick credential type **HashiCorp Vault Secret Lookup**
   - Pick (or create) the matching External Secret Provider that points at `https://vault.acme.com:8200` with the AAP service identity
   - Provide the path (e.g. `secret/aap/prod/ssh/ansible-svc`) and field (e.g. `private_key`)
   - Save
3. **Verify:** Launch any job using that credential — confirm it still works, then check Vault's audit log for the read entry. The credential's stored value in AAP's database is now a reference, not the secret.

### Step 4 — Install `community.hashi_vault` into the AAP EE

1. **What:** Make the Vault lookup plugin available inside the EE that AAP runs playbooks in
2. **How:** Add to the EE's `requirements.yml`:
   ```yaml
   collections:
     - name: community.hashi_vault
       version: ">=7.1.0"
   ```
   Rebuild the EE (`AAP - Build Compliance EE` template, or whatever the customer uses). Push the new image tag. Update the AAP UI's Execution Environment to point at it.
3. **Verify:** Inside a job run with the new EE:
   ```bash
   ansible-galaxy collection list | grep hashi_vault
   ```

### Step 5 — Convert one high-value playbook to use Vault lookups

1. **What:** Replace one hardcoded secret in a playbook with a Vault lookup, end-to-end
2. **How:** Pick a playbook with a clearly-named secret (e.g. ServiceNow service account password in `notify_servicenow_violations.yml`). Replace:
   ```yaml
   snow_password: >-
     {{ vault_snow_password }}
   ```
   with:
   ```yaml
   snow_password: >-
     {{ lookup('community.hashi_vault.vault_kv2_get',
              'aap/prod/servicenow_svc',
              url=vault_addr,
              auth_method='approle',
              role_id=lookup('env','VAULT_ROLE_ID'),
              secret_id=lookup('env','VAULT_SECRET_ID')).data.password }}
   ```
3. **Verify:** Re-run the job template — same outcome (ticket created), but with a Vault audit-log entry showing the read

### Step 6 — Roll out a compatibility shim for the rest of the playbook fleet

1. **What:** Avoid touching every playbook that references `vault_secrets.yml`; instead, swap the resolution path once
2. **How:** Create a shared task file `ansible/tasks/resolve_secret.yml`:
   ```yaml
   - name: Resolve secret '{{ secret_name }}' (Vault if available, vault_secrets.yml fallback)
     ansible.builtin.set_fact:
       "{{ secret_name }}": >-
         {{
           lookup('community.hashi_vault.vault_kv2_get',
                  'aap/' ~ aap_environment ~ '/' ~ secret_name,
                  url=vault_addr, auth_method='approle',
                  role_id=lookup('env','VAULT_ROLE_ID'),
                  secret_id=lookup('env','VAULT_SECRET_ID')).data.value
           if (vault_addr | default('')) != ''
           else hostvars['localhost'][secret_name]
         }}
   ```
   Then each playbook either references the var as before (works without Vault) or includes the shim at the top (works with Vault when configured). Customer can roll out per-environment.
3. **Verify:** Set `vault_addr=''` → playbook uses the file. Set `vault_addr=https://vault.acme.com:8200` → playbook uses Vault.

### Step 7 — Wire the audit log into the customer's SIEM

1. **What:** Every Vault read of an AAP secret is logged; customer's auditors want that log
2. **How:** Vault Enterprise can forward the audit log via the `audit/file/`, `audit/syslog/`, or `audit/socket/` backends — usually syslog into Splunk/Sentinel/Elastic
3. **Verify:** Run an AAP job that lookups a Vault secret; confirm the matching audit entry shows up in the SIEM within the expected SLA

### Step 8 — Document the rotation cadence

1. **What:** AAP's `secret_id` is short-lived by design; AAP's deployment doc must capture how it gets refreshed
2. **How:** Three options the customer picks one of:
   - **Manual rotation** — Vault admin issues a new `secret_id` quarterly; AAP admin updates the External Secret Provider in the UI
   - **Scheduled AAP job** — an AAP job using a higher-privilege token requests a new `secret_id` from Vault on a schedule and updates the External Secret Provider via AAP's REST API
   - **Vault wrapping** — Vault wraps the secret_id; AAP unwraps once at startup. Best paired with Vault's response-wrapping TTL.
3. **Verify:** Force a rotation in a non-prod environment; confirm AAP jobs continue to work

## Playbooks

### Existing in the repo (reuse)

- `ansible/vars/vault_secrets.yml` — the plaintext file Vault is going to replace; reference for which keys land where in Vault
- `ansible/playbooks/rotation_mcp_token.yml` / `rotation_postgres.yml` / `rotation_grafana.yml` / `rotation_update_vault.yml` — the AAC credential-rotation playbooks. Useful pattern reference: they already orchestrate the "rotate + propagate" flow that the Step 8 rotation cadence builds on

### New (to write — for this integration)

- `integrations/hashicorp_vault_enterprise/playbooks/vault_smoke_test.yml` — a 1-task playbook the customer runs to validate AppRole auth + namespace access from inside the EE (used for Step 2 verification)
- `integrations/hashicorp_vault_enterprise/tasks/resolve_secret.yml` — the compatibility shim from Step 6, packaged so playbooks can `include_tasks: ../integrations/hashicorp_vault_enterprise/tasks/resolve_secret.yml`
- `integrations/hashicorp_vault_enterprise/playbooks/rotate_aap_secret_id.yml` — the scheduled-rotation AAP job from Step 8 option B

## Credentials required

| Credential | AAP type | What it grants | Rotation |
|---|---|---|---|
| Vault role_id | static, deploy-time | Non-secret identifier of the AAP role | Only when the role itself is recreated |
| Vault secret_id | dynamic, refreshed | Authenticates AAP as the role; redeemed for a Vault token | Per Vault's policy — typically 24h–7d, customer chooses |
| Vault token (transient) | not stored — held in-memory in the EE | Reads secrets per the `aap-read` policy | Lives only for the duration of a task |
| AAP admin token | already in scope | Updates the External Secret Provider after secret_id rotation | Per AAP's own rotation policy |

The AAP admin's job is to make sure the secret_id never expires
silently; the AAC-style rotation playbooks (`rotation_*.yml`) are the
pattern reference for that work.

## EDA rulebook bits

Not applicable — this integration is a pure pull-from-AAP pattern. No
EDA rulebook needed for the standard case. If the customer wants AAP
to react to Vault audit-log events (e.g. "alert if AAP reads more
than N secrets per hour"), that's a separate SIEM-side integration,
not Vault directly.

## Gotchas

- **Namespace path quirk** — HVE namespaces are passed in the lookup's
  `namespace` argument AND prepended to the API path Vault internally
  resolves. If you also include the namespace in the secret path
  (`namespace/aap/prod/...`) the lookup silently returns the wrong
  value. Pass it only as the named argument.
- **AppRole `secret_id_ttl` mistakes** — if `secret_id_ttl` is 0
  (Vault default) the secret_id is single-use OR forever-valid depending on
  `secret_id_num_uses`. Reading this wrong is the #1 cause of "AAP
  worked yesterday, fails today" reports. Document the customer's
  chosen TTL in their AAP runbook explicitly.
- **EE rebuild churn** — adding `community.hashi_vault` to the EE
  requires a rebuild + push + AAP UI update. Plan for ~30 min of
  downtime or run a parallel EE during cutover.
- **Vault performance replica routing** — multi-DC HVE clusters route
  reads to the nearest replica, but token renewal must go to the
  primary. Configure `url` per environment in `site_config.yml`;
  don't rely on a single global URL.
- **`vault_kv2_get` vs `vault_read`** — for KV v2 secret engines, use
  `vault_kv2_get`. `vault_read` works against KV v1 and other secret
  engines (database, PKI, transit). Mixing them silently returns the
  wrong shape — KV v2 wraps the value under `.data.data.<field>` and
  `.data.metadata.<…>`, while KV v1 returns `.data.<field>` directly.
- **AAP Credential Plugin vs lookup plugin overlap** — both can resolve
  the same secret. Use the AAP Credential Plugin for credentials AAP
  itself manages (Machine, Cloud, SCM); use the lookup plugin for
  per-task secrets that don't fit AAP's credential types (per-API-call
  tokens, per-environment certs, runtime-derived values). Crossing
  the streams adds confusion without value.
- **Audit log volume** — every lookup is one audit-log entry. A
  fleet-scale playbook (1000 hosts × 5 secrets each = 5000 entries
  per run) can swamp a small SIEM. Set the customer's SIEM ingestion
  budget early.
- **403 with no error detail** — if a lookup fails because of a
  missing capability on the path, the Vault response is bare 403 with
  no reason. Always test the `aap-read` policy with the `vault read
  -policy` command before debugging the playbook.
- **Bootstrap chicken-and-egg** — the AAP service identity itself
  (`role_id` + `secret_id`) needs to land on the AAP host somehow.
  AAP's own bootstrap can't read from Vault until it has those.
  Document the chosen Option (A/B/C from Step 2) in the customer's
  install runbook; do NOT leave it implicit.

## Customer-engagement checklist

Before kickoff:
- [ ] Vault Enterprise instance URL provided + reachable from AAP host (test with `curl https://vault.acme.com:8200/v1/sys/health`)
- [ ] Customer's Vault admin has agreed to create the `aap-read` policy + `aap` AppRole
- [ ] Namespace name agreed (e.g. `aap/prod`, `aap/dev`)
- [ ] AAP service identity creation flow documented (who creates the role, who rotates the secret_id)
- [ ] Pre-staged paths in Vault: at minimum `secret/aap/<env>/healthcheck` for smoke-test, plus paths for each named AAP credential to migrate

During implementation:
- [ ] Step 1 verified — bare curl against Vault returns a token
- [ ] Step 2 verified — `vault_kv2_get` lookup returns the smoke-test value
- [ ] Step 3 — one named credential migrated and its job still works
- [ ] Step 4 — EE rebuilt + AAP UI updated; trivial playbook runs with the new EE
- [ ] Step 5 — one playbook migrated to inline Vault lookups; job runs successful
- [ ] Step 6 — `resolve_secret.yml` shim adopted in one additional playbook
- [ ] Step 7 — Vault audit log shows up in customer's SIEM with the expected events

Pre-cutover:
- [ ] All named credentials migrated to External Secret Provider; no plaintext fields remaining
- [ ] Rotation cadence documented and the chosen option from Step 8 is automated
- [ ] Rollback documented: if Vault is unreachable, document the policy decision (fail closed = jobs error; fail open = jobs fall back to plaintext file). Default recommendation: fail closed for prod, fall back for dev.
- [ ] Customer's on-call team trained on what a "Vault failure" looks like in AAP job logs

## AAC compliance sub-case

When the customer adopts AAC for compliance automation, the same
integration carries AAC's runtime secrets — the compliance DB
password, the ServiceNow service-account password (already in
Vault), CyberArk-style high-privilege creds used by remediation
playbooks. The shim from Step 6 means AAC playbooks pick up the
Vault path without per-playbook changes; AAC's existing
`vault_secrets.yml` becomes the dev-environment fallback only.

The Vault audit log captures every AAC read of a secret, which the
FedRAMP / SOC 2 auditor wants to see — same audit-trail benefit AAP
gets, extended to compliance automation.

## References

- HashiCorp Vault docs: https://developer.hashicorp.com/vault/docs
- AppRole auth method: https://developer.hashicorp.com/vault/docs/auth/approle
- `community.hashi_vault` collection: https://galaxy.ansible.com/ui/repo/published/community/hashi_vault/
- AAP Credential Plugin docs: https://docs.ansible.com/automation-controller/latest/html/userguide/credential_plugins.html
- Related entries:
  - [`../aws_ssm/`](../aws_ssm/) — alternative for AWS secrets that live in Parameter Store; some customers split between Vault (cross-cloud secrets) and SSM Parameter Store (per-region cloud secrets)
  - [`../terraform_enterprise/`](../terraform_enterprise/) — TFE has its own Vault integration for run-time secrets; align so secrets aren't duplicated
- Pattern reference: [`../_common/patterns.md`](../_common/patterns.md) § 3 (Pull from AAP)
- Existing AAC rotation pattern (for the Step 8 cadence): `ansible/playbooks/rotation_*.yml`
