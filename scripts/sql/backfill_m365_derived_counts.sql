-- Backfill derived pass/fail counts for cis_m365_v7 rows stored before
-- compliance PR #692 (merged 2026-09-24).
--
-- The bug: persist.yml derived failed-control ids with
--   regex_search(..., '\1') | select('string')
-- but regex_search returns a LIST when group arguments are given, so
-- select('string') dropped every match and failed_controls was always 0 —
-- which also forced passed_controls = controls_evaluated and
-- compliance_percentage = 100. The violations column itself was ALWAYS
-- stored correctly; only the derived counts (and
-- metadata.failed_control_ids) are wrong. This script recomputes them from
-- the stored violations, using the same regex and the same arithmetic as
-- the fixed persist.yml, so backfilled rows are indistinguishable from
-- rows the fixed code writes.
--
-- Scope: rows with the bug signature only — framework 'cis_m365_v7',
-- failed_controls = 0, and at least one stored violation. Rows written
-- after the fix don't match the signature and are never touched. The
-- script is idempotent: a second run matches nothing.
--
-- Usage (run as a user with UPDATE on compliance_results):
--   1. Run the PREVIEW query alone; review the before/after counts.
--   2. Run the UPDATE inside the transaction; compare the reported row
--      count with the preview before COMMIT.
--
-- ─────────────────────────────────────────────────────────────────────
-- PREVIEW — what would change (read-only)
-- ─────────────────────────────────────────────────────────────────────

WITH derived AS (
    SELECT
        r.id,
        r.policy_name,
        r.evaluation_timestamp,
        r.failed_controls   AS old_failed,
        r.passed_controls   AS old_passed,
        r.compliance_percentage AS old_pct,
        COALESCE((r.metadata ->> 'controls_evaluated')::int, r.total_controls) AS denom,
        (r.policy_name = 'cis_m365_v7.attestation') AS is_attestation,
        ARRAY(
            SELECT DISTINCT m[1]
            FROM jsonb_array_elements_text(r.violations) AS v(msg),
                 regexp_matches(v.msg, 'CIS ([0-9]+(?:\.[0-9]+)*)', 'g') AS m
            ORDER BY m[1]
        ) AS failed_ids
    FROM compliance_results r
    WHERE r.framework = 'cis_m365_v7'
      AND r.failed_controls = 0
      AND jsonb_array_length(r.violations) > 0
)
SELECT
    id, policy_name, evaluation_timestamp,
    old_failed, cardinality(failed_ids) AS new_failed,
    old_passed,
    CASE WHEN is_attestation THEN 0
         ELSE greatest(denom - cardinality(failed_ids), 0) END AS new_passed,
    old_pct,
    CASE WHEN is_attestation OR denom = 0 THEN 0
         ELSE round(greatest(denom - cardinality(failed_ids), 0)::numeric
                    / denom * 100, 1) END AS new_pct
FROM derived
ORDER BY evaluation_timestamp, policy_name;

-- ─────────────────────────────────────────────────────────────────────
-- BACKFILL — run after reviewing the preview
-- ─────────────────────────────────────────────────────────────────────

BEGIN;

WITH derived AS (
    SELECT
        r.id,
        COALESCE((r.metadata ->> 'controls_evaluated')::int, r.total_controls) AS denom,
        (r.policy_name = 'cis_m365_v7.attestation') AS is_attestation,
        ARRAY(
            SELECT DISTINCT m[1]
            FROM jsonb_array_elements_text(r.violations) AS v(msg),
                 regexp_matches(v.msg, 'CIS ([0-9]+(?:\.[0-9]+)*)', 'g') AS m
            ORDER BY m[1]
        ) AS failed_ids
    FROM compliance_results r
    WHERE r.framework = 'cis_m365_v7'
      AND r.failed_controls = 0
      AND jsonb_array_length(r.violations) > 0
)
UPDATE compliance_results r
SET failed_controls = cardinality(d.failed_ids),
    passed_controls = CASE WHEN d.is_attestation THEN 0
                           ELSE greatest(d.denom - cardinality(d.failed_ids), 0) END,
    compliance_percentage = CASE
        WHEN d.is_attestation OR d.denom = 0 THEN 0
        ELSE round(greatest(d.denom - cardinality(d.failed_ids), 0)::numeric
                   / d.denom * 100, 1) END,
    metadata = jsonb_set(
        COALESCE(r.metadata, '{}'::jsonb),
        '{failed_control_ids}',
        to_jsonb(d.failed_ids),
        true)
        || jsonb_build_object(
               'derived_counts_backfilled',
               to_jsonb(now()::text))
FROM derived d
WHERE r.id = d.id;

-- The row count reported above must equal the preview's row count.
--
-- THE COMMIT IS YOURS, NOT THIS FILE'S. The transaction is deliberately
-- left open: run this file interactively (psql -f then stay in the
-- session, or paste section by section), compare the counts, and then
-- type COMMIT; yourself — or ROLLBACK; on any mismatch. If you execute
-- the whole file non-interactively and disconnect, PostgreSQL rolls the
-- open transaction back automatically: the fail-closed default is that
-- nothing changes until a human has looked at the numbers.

-- ─────────────────────────────────────────────────────────────────────
-- VERIFY — after commit, the bug signature must match zero rows
-- ─────────────────────────────────────────────────────────────────────

SELECT count(*) AS remaining_bug_signature_rows
FROM compliance_results
WHERE framework = 'cis_m365_v7'
  AND failed_controls = 0
  AND jsonb_array_length(violations) > 0;
