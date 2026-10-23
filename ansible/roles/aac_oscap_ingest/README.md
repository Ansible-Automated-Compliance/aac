# aac_oscap_ingest

Parses an EE-local XCCDF result (or ARF) file with the repo's single, tested
parser — `scripts/openscap_xccdf_parse.py` (see
`tests/test_openscap_xccdf_parse.py`) — and records the result through
**`aac_store_results`**, so OpenSCAP evidence is waiver-aware,
evidence-provenanced, and historically tracked like every other AAC finding.
Extracted from the proven `openscap_assess.yml` (#536) pipeline.

Results are ingested faithfully under their **own framework key** (default
`openscap_<profile-suffix>`), never silently merged into a Rego framework key
— each failed rule's CCE/CCI idents are stored as the hook for an explicit
crosswalk later. Refuses a file with zero evaluated rules (green-but-empty
guard).

**Transition on-ramp:** the parser matches XCCDF elements by local name, so
externally produced files — `oscap-podman`, DISA content, **CIS-CAT Pro**
ARF — ingest identically. Point `oscap_results_file` at the file and set
`oscap_tool` so reporting can distinguish assessors, without running a scan.

## Variables

| Variable | Criticality | Default | How to supply |
|---|---|---|---|
| `oscap_results_file` | **CRITICAL — required** | set by `aac_oscap_scan` | Explicit extra_vars path when ingesting an externally produced XCCDF/ARF |
| `framework_label` | HIGH | `""` → `openscap_<profile-suffix>` derived from the parsed profile, column-safe ≤90 chars | extra_vars. Never point at a Rego framework key unless deliberately merging evidence sources |
| `oscap_tool` | MEDIUM | `openscap` | extra_vars — e.g. `cis-cat-pro` for external files (stored in `metadata.tool`) |
| `record_to_db` | LOW | `true` | extra_vars |
| `oscap_cleanup_fetched` | LOW | `true` | extra_vars — remove the EE-local file after ingest |
| `profile_id` / `datastream_path` / `tailoring_path` / `oscap_version` | LOW | from `aac_oscap_scan` when chained; `""` otherwise | provenance metadata only |

Plus the `aac_store_results` DB connection vars (`pg_host` etc.) via
`site_config.yml` — this role sets only the `aac_result_*` payload.

## Run context

Runs in the EE (`delegate_to: localhost, become: false` from the calling
play) — the fetched file is EE-local and `community.postgresql` executes from
the EE.
