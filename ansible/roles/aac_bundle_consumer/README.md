# aac_bundle_consumer

Pulls the tenant's **signed customer-policy bundle** from the AAC Customer
Portal, verifies the ed25519 envelope offline, swaps it into a **dedicated
`opa-customer` container** (default port 8184), and acks the outcome back to
the portal's delivery timeline (`bundle_delivery_events`, portal migration 034).

This is the AAC-side consumer that closes portal gap **G8 / AAC task #45**
(OPA bundle mode). The portal builds/signs/serves bundles; this role is "how
the bridge swaps it into a running OPA".

## Why a dedicated container

The portal builds bundles with `opa build` and **no scoped roots manifest** —
an OPA bundle without roots owns the entire data/policy namespace of the
server it loads into. Loading it into `opa-security`/`opa-compliance`/`opa-ot`
would clobber the REST-loaded framework policies. Customer policies therefore
get their own OPA on the next port in the sequence (8184), and callers query
`http://<aac_host>:8184/v1/data/customer/...`.

## Flow

1. Fetch `GET /bundles/current/envelope` (bearer, scope `policy_bundle_pull`)
2. Verify ed25519 signature over the canonical payload with the **pinned**
   portal public key (`files/verify_envelope.py`; offline — air-gap friendly)
3. Fetch bundle bytes **by the verified sha** (this also records a `pulled`
   event server-side), re-hash locally, compare to the signed sha256
4. Keep the previous bundle as `.prev`, install the new one atomically
5. Recreate `opa-customer` with `opa run --server --bundle`, wait for `/health`
6. `POST .../bundles/{sha}/delivery {event: loaded, opa_endpoint, opa_version}`

On any failure the rescue path restores `.prev`, restarts the container, acks
`load_failed` with the error (so the portal timeline shows the truth), and
re-raises.

## Variables — what to supply and how

Per role-config discipline: no environment values ship in the role.

**Two naming schemes work**: canonical `aac_bundle_*` (site_config.yml /
inventory) and short `portal_*` (AAP survey / extra_vars). The role defaults
fall back to the `portal_*` form lazily; `aac_bundle_*` wins when both are set.

| Variable (portal_* fallback) | Required | Supply via | Notes |
|---|---|---|---|
| `aac_bundle_portal_url` (`portal_url`) | **yes** | site_config.yml or extra_vars/survey | e.g. `https://<portal-host>` |
| `aac_bundle_tenant_id` (`portal_tenant_id`) | **yes** | site_config.yml or extra_vars/survey | tenant UUID; the signed envelope's tenant must match or the role refuses |
| `aac_bundle_token` (`portal_bundle_pull_token`) | **yes** | **vault_secrets.yml or AAP credential** | scope `policy_bundle_pull`; never plaintext; all token-bearing calls are `no_log` |
| `aac_bundle_signing_pubkey_b64` (`portal_signing_pubkey_b64`) | production: **yes** | site_config.yml (pin at onboarding) | empty ⇒ **fails closed** unless `aac_bundle_allow_tofu=true` |
| `aac_bundle_allow_tofu` (`portal_allow_tofu`) | default `false` | extra_vars (lab bring-up only) | persisted TOFU: first fetched key is stored at `<dir>/pinned_signing_key.b64` and ENFORCED on later runs — a changed key is a hard failure |
| `aac_bundle_signing_key_id` (`portal_signing_key_id`) | recommended | site_config.yml | envelope `key_id` must match when set |
| `aac_bundle_token_id` (`portal_bundle_token_id`) | optional | vault/site_config | `X-Token-Id` header on every portal call |
| `aac_bundle_runtime_host` (`portal_runtime_host`) | default `aac_host` | site_config.yml | the SSH-reachable podman host; override where `aac_host` names a route/VIP rather than the RHEL box |
| `aac_bundle_validate_certs` (`portal_validate_certs`) | default `true` (secure) | site_config.yml | lab CRC self-signed routes set `false` explicitly; never in a customer profile |
| `aac_bundle_allow_insecure_tofu` (`portal_allow_insecure_tofu`) | default `false` | extra_vars (lab bring-up only) | TOFU over unverified TLS is refused unless this is set — MITM could otherwise supply key AND bundle |
| `aac_bundle_dir` | default `/etc/opa/customer` | — | bundle + `.prev` + `.incoming` + TOFU pin live here (0755/0644 — rootless podman must read them) |
| `aac_bundle_container_name` / `aac_bundle_port` | defaults `opa-customer` / `8184` | — | name is regex-validated (`^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`); port continues the 8181–8183 sequence |
| `aac_bundle_opa_image` | default `docker.io/openpolicyagent/opa@sha256:1b9ca9be…` (digest-pinned; = opa 1.20.2) | — | never a mutable tag; bump deliberately by pasting the new verified digest |
| `aac_bundle_generate_systemd` | default `true` | — | unit install FAILS loudly if it can't complete; opt out per-host instead |

## Invocation

Playbook: `ansible/playbooks/sync_customer_bundle.yml`. **Create an AAP job
template for it** (suggested name "AAC - Sync Customer Policy Bundle") — no
seeder currently creates this template, so it's a one-time manual add per
controller. **Keep `allow_simultaneous` OFF** (the AAP default): the
template's serialization is the role's concurrency control — two overlapping
runs against the same host would race the bundle swap.

`site_config.yml` / `vault_secrets.yml` are optional at parse time (loaded via
`first_found`, skipped when absent), so extra_vars-only invocation works on a
freshly bootstrapped AAP.

Re-run any time the tenant builds a new bundle in the portal; the run is
idempotent for an unchanged sha (same bytes, container recreated on the same
bundle). On failure, the rescue restores the previous bundle, **recreates**
the container on it, verifies health, and acks `load_failed` with the error.

## Tests

The envelope verifier is the trust boundary and has CLI-level tests that run
the real `files/verify_envelope.py` via subprocess (valid / tampered payload /
tampered signature / malformed JSON / key-id mismatch / wrong key):

```bash
python3 ansible/roles/aac_bundle_consumer/tests/test_verify_envelope.py
```

## Verifying it worked

```bash
curl -s http://<aac_host>:8184/health            # 200
curl -s http://<aac_host>:8184/v1/data/customer  # tenant policy tree
```

Portal side: the bundle's history row shows `loaded` in the Delivery column,
and `GET /api/portal/v1/me/bundles/{id}/delivery` lists pulled → loaded.
