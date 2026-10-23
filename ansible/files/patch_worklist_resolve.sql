-- patch_worklist_resolve.sql — turn the pulled Portal patch manifest into a
-- per-host work list.
--
-- Runs entirely set-based off the newest `patch_manifest_raw` row. Two joins
-- happen here, and both are recorded in the output so a reviewer can see how a
-- row was derived:
--
--   1. HOST RESOLUTION (`host_resolution`)
--      The manifest carries {vendor, product, installed_version} + a host_count.
--      Those are exactly the GROUP BY keys `inventory_catalog` used to aggregate
--      `installed_inventory`, so the aggregation reverses losslessly.
--        auto   — matched back to installed_inventory rows (per-host packages)
--        manual — matched a manual_product_declarations row; hosts come from
--                 its affected_hosts[] array (appliances, firmware, network OS)
--
--   2. FIX SELECTION (`fix_match`)
--      A CVE may carry fixes from several vendors. `fixes[].vendor` is the CVE
--      vendor namespace (redhat, ubuntu, nodejs) — a DIFFERENT namespace from
--      the inventory `vendor` (which is lower(package_name) on Linux), so the
--      two must never be joined directly. Instead each candidate fix is ranked
--      against the host:
--        os_family — the fix vendor matches the host's OS family (best)
--        registry  — a language-registry fix (npm/pip); OS-independent
--        sole      — only one fix offered for this CVE, so it is unambiguous
--        ambiguous — several fixes, none matched; the first is taken, flag it
--        none      — the CVE carries no fix at all; the host is still listed
--
-- An affected host with no known fix is deliberately KEPT (fix_match='none').
-- Dropping it would hide exposure.

TRUNCATE patch_worklist;

INSERT INTO patch_worklist (
    pulled_at, cve_id, severity, kev_member,
    hostname, os_family, vendor, product, installed_version,
    fix_vendor, fixed_version, package_manager, install_command,
    patch_source, advisory_id, advisory_url, artifact_url,
    host_resolution, fix_match
)
WITH latest AS (
    SELECT manifest, pulled_at
      FROM patch_manifest_raw
     ORDER BY id DESC
     LIMIT 1
),
cve AS (
    SELECT l.pulled_at,
           item->>'cve_id'                              AS cve_id,
           item->>'severity'                            AS severity,
           COALESCE((item->>'kev_member')::boolean, false) AS kev_member,
           item->'installed'                            AS installed,
           COALESCE(item->'fixes', '[]'::jsonb)         AS fixes
      FROM latest l,
           LATERAL jsonb_array_elements(l.manifest->'items') item
),
-- The affected {vendor, product, version} tuples, one row each.
affected AS (
    SELECT c.pulled_at, c.cve_id, c.severity, c.kev_member, c.fixes,
           inst->>'vendor'            AS vendor,
           inst->>'product'           AS product,
           inst->>'installed_version' AS installed_version
      FROM cve c,
           LATERAL jsonb_array_elements(c.installed) inst
),
-- Auto rows: reverse the catalog aggregation against per-host inventory.
hosts_auto AS (
    SELECT a.pulled_at, a.cve_id, a.severity, a.kev_member, a.fixes,
           a.vendor, a.product, a.installed_version,
           ii.hostname,
           ii.os_family,
           'auto'::varchar AS host_resolution
      FROM affected a
      JOIN installed_inventory ii
        ON ii.package_vendor  = a.vendor
       AND ii.package_name    = a.product
       AND ii.package_version = a.installed_version
),
-- Manual rows: operator-declared products carry their own host list.
hosts_manual AS (
    SELECT a.pulled_at, a.cve_id, a.severity, a.kev_member, a.fixes,
           a.vendor, a.product, a.installed_version,
           h                AS hostname,
           NULL::varchar    AS os_family,
           'manual'::varchar AS host_resolution
      FROM affected a
      JOIN manual_product_declarations d
        ON d.vendor  = a.vendor
       AND d.product = a.product
       AND d.version = a.installed_version,
           LATERAL unnest(d.affected_hosts) h
),
hosts AS (
    SELECT * FROM hosts_auto
    UNION ALL
    SELECT * FROM hosts_manual
),
-- Rank every candidate fix against the host. LEFT JOIN keeps fixless CVEs.
ranked AS (
    SELECT h.*,
           f->>'vendor'          AS fix_vendor,
           f->>'fixed_version'   AS fixed_version,
           f->>'package_manager' AS package_manager,
           f->>'install_command' AS install_command,
           f->>'source'          AS patch_source,
           f->>'advisory_id'     AS advisory_id,
           f->>'advisory_url'    AS advisory_url,
           CASE
               WHEN f IS NULL THEN 5
               WHEN (lower(COALESCE(h.os_family, '')) = 'redhat'
                     AND lower(f->>'vendor') IN ('redhat','rhel','centos','rocky','almalinux','oracle'))
                 OR (lower(COALESCE(h.os_family, '')) = 'debian'
                     AND lower(f->>'vendor') IN ('ubuntu','debian'))
                 OR (lower(COALESCE(h.os_family, '')) = 'suse'
                     AND lower(f->>'vendor') IN ('suse','opensuse','sles'))
                 OR (lower(COALESCE(h.os_family, '')) = 'windows'
                     AND lower(f->>'vendor') IN ('microsoft','windows'))
                   THEN 1
               WHEN f->>'source' = 'registry' THEN 2
               WHEN jsonb_array_length(h.fixes) = 1 THEN 3
               ELSE 4
           END AS fix_rank
      FROM hosts h
      LEFT JOIN LATERAL jsonb_array_elements(
               CASE WHEN jsonb_array_length(h.fixes) > 0 THEN h.fixes END) f ON TRUE
)
SELECT DISTINCT ON (cve_id, hostname, vendor, product, installed_version)
       pulled_at, cve_id, severity, kev_member,
       hostname, os_family, vendor, product, installed_version,
       fix_vendor, fixed_version, package_manager, install_command,
       patch_source, advisory_id, advisory_url,
       NULL::text AS artifact_url,   -- the Portal hosts no binaries, by design
       host_resolution,
       CASE fix_rank
           WHEN 1 THEN 'os_family'
           WHEN 2 THEN 'registry'
           WHEN 3 THEN 'sole'
           WHEN 4 THEN 'ambiguous'
           ELSE 'none'
       END AS fix_match
  FROM ranked
 -- The trailing columns are tie-breakers, not cosmetics. fix_rank alone is not
 -- unique: a CVE can carry two fixes that both match the host's os_family
 -- (e.g. redhat + rocky on a RedHat host), and DISTINCT ON would then pick
 -- whichever row the planner happened to emit first — so the chosen
 -- install_command could change between otherwise identical runs. Ordering on
 -- the fix's own identity after fix_rank makes the choice deterministic.
 ORDER BY cve_id, hostname, vendor, product, installed_version,
          fix_rank,
          COALESCE(fix_vendor, ''),
          COALESCE(fixed_version, ''),
          COALESCE(advisory_id, '');
