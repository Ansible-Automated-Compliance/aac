# Evidence Immutability

**Version:** v1.1
**Date:** 2026-10-09
**Authors:** Tim Coulter · Claude (Anthropic)
**Scope:** `compliance_results`, `compliance_certifications`, and the maintenance log that guards them.

---

## The claim, stated precisely

AAC's documents have said the evidence store is "immutable" since the first solution
architecture. Until this change that was true only by convention: nothing in the database
prevented an `UPDATE` or `DELETE`, every assessment playbook wrote as the database owner
or superuser, and one maintenance script had already rewritten historical rows in place.

The claim is now backed by three mechanisms, each covering a failure the others cannot:

| Mechanism | What it stops | What it cannot stop |
|---|---|---|
| **Append-only guard** (trigger) | Any `UPDATE`/`DELETE` on an evidence table, by any role, unless the session declares maintenance | A superuser or table owner dropping the trigger |
| **Evidence writer role** (`compliance_writer`: SELECT everywhere, INSERT on the two evidence tables only) | Assessment runs rewriting evidence even with the guard gone; a compromised playbook credential rewriting history or forging the maintenance log | Someone holding the owner or superuser credential |
| **Hash chain** (`row_hash` = SHA-256 of the row plus the previous row's hash) | Silent alteration: any change to any chained row is detected by `evidence_chain_verify()` at that row | A superuser who rewrites a row *and* recomputes every later hash — which is why the chain head is published outside the database |

The honest statement for external use: *the evaluation path only appends; the database
refuses rewrites; the writer the platform uses cannot rewrite; and any rewrite by a
privileged administrator is detectable.* Not "cannot be altered by anyone."

## 1. Append-only guard

`ansible/files/evidence_append_only.sql`, applied by `aac_compliance_db` on every run,
installs `trg_compliance_results_append_only` and `trg_compliance_certifications_append_only`.
Both call `evidence_append_only_guard()`, which raises `insufficient_privilege` on `UPDATE`
or `DELETE`:

```
compliance_results is append-only: UPDATE refused. Corrections are new rows
(supersedes = old id). Deliberate maintenance must SET aac.evidence_maintenance = 'on'
and is logged.
```

The same guard, without any escape, protects `evidence_maintenance_log` itself.

One in-place write is allowed on `compliance_certifications` because it is a link, not a
rewrite: setting `superseded_by` from NULL to a value when nothing else in the row changes.
Re-linking, or changing any other column, is refused like any other update.

## 2. Corrections are new rows

`compliance_results.supersedes` points at the row a correction replaces. The old row
stays. `compliance_results_current` is the table minus superseded rows; read it for
posture and the table for history. A correction row should carry what it corrects and why
in `metadata` (the convention from the integrity assessment: a `_correction` object with
`at`, `action`, `by`).

`compliance_certifications` already had `superseded_by` for the same purpose.

## 3. The maintenance path

There are legitimate reasons to touch history: a migration that backfills a column that
should always have been populated, for example. The sanctioned way:

```sql
SET aac.evidence_maintenance = 'on';
SET aac.evidence_maintenance_note = 'why, by whom, which ticket';
UPDATE compliance_results SET ... WHERE ...;
```

Both settings are required: maintenance with a blank note is refused, so there is no
sanctioned rewrite without a recorded reason. The guard then writes the **complete previous
row** to `evidence_maintenance_log` with the time, database user, client address, operation
and note. Nothing can delete that log entry. The hash chain breaks at every touched row, on
purpose: the verifier names them, and the log explains them. A rewrite that is not in the
log is tampering.

`ansible/files/evidence_integrity_fix.sql` (the framework-attribution backfill) runs
through this path and says so at its top.

## 4. The evidence writer role

`aac_compliance_db` creates `compliance_writer` when `compliance_writer_password` is in
the vault: `LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB`, `SELECT` on all tables, `INSERT`
on `compliance_results` and `compliance_certifications` only, `USAGE` on their sequences,
nothing else; default privileges for tables created later are `SELECT` only. In
particular the writer cannot insert into `evidence_maintenance_log`, so a leaked writer
credential cannot forge the audit trail. The role task then checks **effective**
privileges with `has_table_privilege()` (which sees `PUBLIC` grants and role membership,
unlike the ACL catalog) and fails the run if the role is a superuser, can update, delete
or truncate an evidence table, can insert into the log, or cannot insert evidence.

To store evidence as this role, set in `site_config.yml`:

```yaml
aac_evidence_writer_user: "compliance_writer"
```

Every evidence write path then authenticates as the writer using
`compliance_writer_password`: the two store roles, and the playbooks that insert into
`compliance_results` directly, all through the shared selection in
`ansible/vars/evidence_writer.yml`. Nothing else changes user. On an upgrade install
with no writer password in the vault the DB role prints a visible note and skips the role;
nothing breaks, and the note says what to add.

## 5. The hash chain

`trg_compliance_results_chain` runs before every insert into `compliance_results`:

1. takes a transaction-scoped advisory lock so concurrent writers serialise on the chain;
2. allocates `chain_seq`, the row's position in the chain, **inside** the lock. The `SERIAL`
   id cannot serve as the order: it is allocated by the column default before any trigger
   runs, so two concurrent inserts can take ids in one order and the lock in the other;
3. reads the `row_hash` of the highest `chain_seq` (or the genesis value, 64 zeros);
4. sets `prev_hash` to it and `row_hash` to `SHA-256(evidence_row_canonical(row))`.

`evidence_row_canonical()` concatenates every evidence column with explicit `<null>`
markers and a version tag (`aac-evidence-v1`), `prev_hash` included and `row_hash`
excluded. It is a public contract: changing it invalidates every hash, so a column that
must join the canonical form is appended at the end under a new version tag and the
corpus is re-anchored through the maintenance path.

On an existing install the script anchors every pre-existing row once, in `id` order.
Those hashes attest to the rows' content from the moment of anchoring forward, not before.

## 6. Verification

`evidence_chain_verify()` walks the table in `chain_seq` order, recomputes every link, and
returns one row: total, chained, unhashed and broken counts, the first broken id, the
head id and hash, and whether all four guard triggers are present and enabled on their
exact tables. An unhashed row counts as a break: after anchoring, a row outside the chain
is an anomaly (a disabled trigger, a privileged insert), not a gap to skip.

`ansible/playbooks/verify_evidence_chain.yml` runs it, checks the four guard triggers, checks
the writer role's effective privileges (and fails if a configured writer does not exist),
lists maintenance-log entries in the last 24 hours, and publishes the head id and hash
through `set_stats`. It runs from an AAP project checkout: local config is optional and
the connection can come from extra vars and the vault credential. Scheduled daily from AAP, the job
artifacts become a record outside the database of what the chain head was each day; an
auditor compares a current head against a recorded one. The playbook fails on any broken
link, missing or disabled guard, or a writer that can rewrite. Logged maintenance rewrites
are reported, not failed, unless `evidence_chain_fail_on_maintenance=true`.

`verify_install.yml` carries a hard GO/NO-GO check that the guard is present.

## 7. Operating notes

- **Do not disable the triggers to "fix" a row.** Use the maintenance path; it exists so
  that the fix is on the record.
- **Backups of the table are not evidence.** `compliance_results_bk_*` tables created by
  the integrity script are unguarded copies; the guarded table is the record.
- **Re-anchoring** after a canonical-form change is a maintenance operation: declare it,
  note it, re-run the anchoring block, and record the new head in that day's verifier run.
- **What a broken link looks like in practice:** `verify_evidence_chain.yml` fails with the
  first broken id. Look that id up in `evidence_maintenance_log`. If it is there, read the
  note and move on. If it is not, the row was changed outside the sanctioned path.

---

*Co-authored by Claude (Anthropic) via Claude Code, per the AAC AI-authorship convention.
Bump the version on every revision.*
