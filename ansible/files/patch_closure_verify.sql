-- patch_closure_verify.sql — re-measure the estate and decide, per finding,
-- whether the exposure actually closed.
--
-- Run AFTER fact collection and `refresh_inventory_catalog.yml` have refreshed
-- `installed_inventory`, so the comparison is against current truth rather than
-- the same snapshot that produced the worklist.
--
-- Appends, never truncates: this table is the evidence trail. A finding
-- verified weekly produces a row per verification, which is what lets an
-- assessor see *when* it closed rather than only that it is closed now.
--
-- ── On the deliberately conservative rule ────────────────────────────────────
-- `changed_review` is NOT counted as closed. If a version moved but does not
-- equal the fixed version, that could be a newer build that includes the fix, or
-- an unrelated upgrade that does not. **A version-string comparison in SQL
-- cannot distinguish those**, and RPM epoch/version/release ordering is not
-- expressible here. Claiming closure on a string mismatch would manufacture
-- exactly the false assurance this loop exists to prevent, so it is surfaced for
-- human review instead. Under-claiming is the correct failure direction for an
-- evidence artifact.

INSERT INTO patch_closure_evidence (
    cve_id, severity, kev_member, hostname, vendor, product,
    version_at_finding, version_now, fixed_version, outcome, evidence_note
)
WITH current_state AS (
    -- What the host reports NOW for each product named in the worklist.
    SELECT w.cve_id, w.severity, w.kev_member, w.hostname,
           w.vendor, w.product,
           w.installed_version AS version_at_finding,
           w.fixed_version,
           ii.package_version  AS version_now,
           EXISTS (SELECT 1 FROM installed_inventory h
                    WHERE h.hostname = w.hostname)          AS host_reports,
           (ii.package_version IS NOT NULL)                 AS product_present
      FROM patch_worklist w
      LEFT JOIN installed_inventory ii
             ON ii.hostname       = w.hostname
            AND ii.package_vendor = w.vendor
            AND ii.package_name   = w.product
)
SELECT cve_id, severity, kev_member, hostname, vendor, product,
       version_at_finding, version_now, fixed_version,
       CASE
           WHEN NOT host_reports        THEN 'host_absent'
           WHEN NOT product_present     THEN 'closed_removed'
           WHEN fixed_version IS NOT NULL
                AND version_now = fixed_version      THEN 'closed_exact'
           WHEN version_now IS DISTINCT FROM version_at_finding
                                                     THEN 'changed_review'
           ELSE 'still_exposed'
       END AS outcome,
       CASE
           WHEN NOT host_reports THEN
               'Host reports no inventory. Closure cannot be proven; confirm the host '
               'was decommissioned rather than simply failing to report.'
           WHEN NOT product_present THEN
               format('Product %s is no longer installed on %s. Exposure removed by '
                      'removal rather than by patching.', product, hostname)
           WHEN fixed_version IS NOT NULL AND version_now = fixed_version THEN
               format('Re-measured: %s is now at %s, the version that fixes %s. '
                      'Exposure closed and proven.', product, version_now, cve_id)
           WHEN version_now IS DISTINCT FROM version_at_finding THEN
               format('Version moved %s -> %s but does not equal the fixed version %s. '
                      'NOT counted as closed: a string comparison cannot tell a newer '
                      'fixed build from an unrelated upgrade. Requires human review.',
                      version_at_finding, version_now, coalesce(fixed_version,'(unknown)'))
           ELSE
               format('Still at %s. The remediation did not take effect on %s.',
                      version_now, hostname)
       END AS evidence_note
  FROM current_state;
