-- support_status_resolve.sql — derive per-host support status
--
-- Joins what we observe (installed_inventory) to what upstream publishes
-- (product_lifecycle) through the operator map, and assigns a lifecycle stage.
--
-- Stage definitions, in evaluation order. `support_end_date` is the end of
-- ACTIVE support; `eol_date` is the end of ALL support including extended.
-- The gap between them is real and worth naming: a product in that window still
-- gets security fixes but no feature work, which is a plan-the-refresh signal
-- rather than an act-now one.
--
--   unsupported  eol already passed, or upstream flagged it with no date.
--                NO PATCH WILL EVER COME. Remediation debt has become
--                REPLACEMENT debt. Exposure here never decays.
--   sunset       eol within 365 days. Patches still flow, but replacement has
--                to be funded now, not at the deadline.
--   mature       active support ended, eol still more than a year out.
--                Security fixes only. Plan the refresh.
--   current      in active support.
--   unknown      product is mapped but upstream has no matching cycle — usually
--                a version we could not parse, or a cycle upstream dropped.
--                Surfaced rather than hidden, because "we don't know" is a
--                finding in its own right for an SA-22 assessment.
--
-- Not derivable from a lifecycle feed, and therefore NOT assigned here:
--   obsolete   — no longer sold and no successor product exists
--   orphaned   — vendor gone or project abandoned
-- Both need signals a lifecycle date cannot supply (repository archive state,
-- discontinuation notices). They are part of the model but are operator-flagged,
-- and claiming to derive them from `eol` alone would be dishonest.

TRUNCATE host_support_status;

INSERT INTO host_support_status (
    hostname, match_kind, product, eol_product,
    observed_version, cycle, lifecycle_stage, eol_date, days_to_eol
)
WITH observed AS (
    -- OS-level: one row per host. The version lives on every inventory row for
    -- that host, so collapse to a single observation per (host, os_family).
    SELECT DISTINCT
           ii.hostname,
           'os'::varchar        AS match_kind,
           ii.os_family         AS product,
           ii.os_version        AS observed_version
      FROM installed_inventory ii
     WHERE ii.os_family IS NOT NULL
       AND ii.os_version IS NOT NULL

    UNION ALL

    -- Package-level: only packages the operator has chosen to track.
    SELECT DISTINCT
           ii.hostname,
           'package'::varchar   AS match_kind,
           ii.package_name      AS product,
           ii.package_version   AS observed_version
      FROM installed_inventory ii
      JOIN support_status_map m
        ON m.match_kind = 'package'
       AND m.aac_key    = ii.package_name
),
mapped AS (
    SELECT o.*,
           m.eol_product,
           m.cycle_mode,
           -- Derive the upstream release cycle from the observed version.
           CASE m.cycle_mode
               WHEN 'major'      THEN split_part(o.observed_version, '.', 1)
               WHEN 'majorminor' THEN
                   CASE WHEN strpos(o.observed_version, '.') > 0
                        THEN split_part(o.observed_version, '.', 1) || '.' ||
                             split_part(o.observed_version, '.', 2)
                        ELSE o.observed_version
                   END
               ELSE o.observed_version
           END AS cycle
      FROM observed o
      JOIN support_status_map m
        ON m.match_kind = o.match_kind
       AND m.aac_key    = o.product
),
joined AS (
    SELECT mp.*,
           pl.eol_date,
           pl.eol_is_past,
           pl.support_end_date
      FROM mapped mp
      LEFT JOIN product_lifecycle pl
        ON pl.eol_product = mp.eol_product
       AND pl.cycle       = mp.cycle
)
SELECT hostname, match_kind, product, eol_product,
       observed_version, cycle,
       CASE
           WHEN eol_is_past                              THEN 'unsupported'
           WHEN eol_date IS NOT NULL
                AND eol_date <= CURRENT_DATE             THEN 'unsupported'
           WHEN eol_date IS NOT NULL
                AND eol_date <= CURRENT_DATE + 365       THEN 'sunset'
           WHEN support_end_date IS NOT NULL
                AND support_end_date <= CURRENT_DATE     THEN 'mature'
           WHEN eol_date IS NOT NULL                     THEN 'current'
           ELSE 'unknown'
       END AS lifecycle_stage,
       eol_date,
       CASE WHEN eol_date IS NOT NULL
            THEN (eol_date - CURRENT_DATE)::int
       END AS days_to_eol
  FROM joined;
