# GitGuardian Incident Triage — Runbook

**Owners:** Tim, Juan
**Installed:** 2026-10-01, all three repos (compliance, rego_policy_libraries, AAC_Customer_Portal)
**Objective:** find data leakage before a customer notifies us. The dashboard
only serves that objective if its signal stays clean — triage every incident,
never let them pile up as "Triggered."

## The decision tree

For every new incident, in order:

1. **Is the secret real and potentially live?**
   - Real + possibly live → **rotate/revoke FIRST**, then purge from history
     using the documented force-push procedure (see
     `sce-scan-history-rewrite` notes: ruleset + branch-protection gates,
     `git-filter-repo`, atomic force-push, restore gates). Rotation kills the
     risk; the purge is scanner hygiene. Never purge-without-rotate.
   - Real but the issuing system no longer exists (decommissioned host,
     reinstalled AAP) → dead credential. Scrub from the working tree if still
     present, resolve the incident with a note naming the dead system.
2. **Is it a placeholder, template, or sample?**
   - `$VAR` / `YOUR_*` / template vault files / vendor sample data
     ("Contoso"-class) → resolve as **false positive / sample**. If it's in
     the current tree, prefer converting to `$VAR` form so future pushes stop
     re-flagging (that's what the 2026-10-01 sweep did).
3. **Is it a test fixture?** (GitGuardian usually labels these "Test file")
   → resolve as test data. Fixtures should look obviously fake; if a fixture
   could pass for real, make it obviously fake in a follow-up PR.
4. **Is it history-only?** (file absent or clean at HEAD)
   → resolve with "removed at HEAD; history purge batched." Pending batch:
   k8s-secret manifest + scrubbed cred strings + the PR #383 Sigstore example
   blob — do these ONCE together with the GitHub Support GC request, not as
   repeated force-pushes.

## Starter map — the initial historical scan (2026-10-01, 28 incidents)

Triage of the first dashboard page, verified against the trees the same day:

| Incident (dated by commit) | Verdict | Dashboard action |
|---|---|---|
| Curl Username Password ×26 + ×98 — compliance docs/CLAUDE.md | Placeholder-pattern matches; live tree converted to `$VAR` form in the 2026-10-01 sweep | Resolve as FP after the sweep PR merges |
| Bearer Token ×6 — `docs/architecture/AAP_OPA_INTEGRATION_ARCHITECTURE.md` (Jul 9) | **Real token string**, but issued by the pre-CRC containerized AAP, decommissioned — dead. Scrubbed from the tree in the sweep | Resolve: dead issuer, scrubbed |
| Generic Password ×45 — `vault_secrets.yml` (+1) (Aug 26) | Two files: `ansible/vars/` one purged from remote history 2026-09-22 (GC ticket pending); `install/existing-aap-extended/` one was a placeholder TEMPLATE (~24 keys, placeholder-marked), dir deleted at HEAD | Resolve: known 9/22 incident + template; final purge batched with GC |
| Username Password ×10 — infoblox demo playbook (Sep 1) | File gone at HEAD; demo credentials, lab-only | Resolve: history-only, batched purge |
| Generic Password ×6 — `scripts/install_postgres.sh` (Aug 28) | Current script does variable handling/prompts; literal was an old revision | Resolve: fixed at HEAD |
| Generic High Entropy ×2, ×7 — portal test files | Test fixtures (GitGuardian labeled "Test file") | Resolve: test data |
| Generic Password ×2 — portal `bootstrap_demo_local.sh` (Jun 10) | Current script generates random passwords (`secrets.token_urlsafe`) | Resolve: fixed at HEAD |
| Generic Password ×1 HIGH, **publicly exposed** — rego `sample_m365_facts.json` (Jun 2) | Microsoft's own sample data ("Contoso", "Spring2026" — canonical example banned-password list) in a dummy M365 facts fixture; file gone at HEAD | Resolve: vendor sample data |

## Known residual scanner noise (do not "fix", documented by design)

`.gitleaks.toml` deliberately allowlists only value-stopword fixtures — no
path excludes, no fingerprints — accepting residual report noise over the risk
of hiding a real secret. Current known-FP set (all credential-free lines):
three `COMPLETE_INSTALLATION_GUIDE.md` lines (table/comment rows). The lab
health-check skill and `reset-demos.sh` (`${VAR:?}` forms) moved out of this
repository on 2026-10-17 and no longer appear. Re-triage, don't suppress.

## What GitGuardian does NOT cover

- **Lab IP bleed** (lab-subnet addresses in docs/demos) — it detects
  secrets, not identifiers. The pre-commit sensitive-data scanner and the
  code-review rule are the only nets for that class.
- **Push protection on the private repos** needs GHAS (paid); it is enabled
  free on the public rego repo. Until a GHAS decision, the pre-commit hook +
  weekly `security-scan.yml` gitleaks run are the private-repo guards.

## Cadence

- New incidents: triage within the week (they appear in the Monday standards
  report's blockers section if left "Triggered" > 7 days — add once the
  report routine gains GitGuardian API access).
- Quarterly: re-run a local full-history scan (`gitleaks git <repo> --redact`)
  and reconcile against the dashboard.
