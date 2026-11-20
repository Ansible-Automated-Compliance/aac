-- cve_cache_schema.sql — the AAC-side CVE cache: what the patch-intelligence
-- playbooks match the installed inventory against.
--
-- Idempotent: safe to run on every install and on every playbook start.
--
-- OWNERSHIP. These two tables belong to the AAC evidence database (this role),
-- not to the customer portal. The portal keeps its own `cve_events` and its own
-- `cve_vendor_remediations` (keyed by vendor_id, api/migrations/005 there) in
-- its own database; it DELIVERS rows into this cache over the bridge. The two
-- `cve_vendor_remediations` share a name and nothing else: this one carries
-- the vendor as text and is keyed (cve_id, vendor). A CVE may carry one fix
-- per vendor; identify_affected_components.yml and simulate_patch_lifecycle.yml
-- therefore select exactly ONE row per matched component (LATERAL ... LIMIT 1,
-- preferring the installed package's vendor), never a bare join on cve_id.
-- They never live in the same database, so there is one owner per table.
--
-- Populated by: the portal bridge, the EDA CVE webhook, the opt-in
-- ansible/playbooks/fetch_redhat_cve_data.yml (Red Hat Security Data API,
-- source='redhat_security_data_api'), or — for a demo —
-- ansible/files/demo_cve_fixture.sql (synthetic ids, source='demo_seed'),
-- applied ONLY by ansible/playbooks/seed_demo_cve_fixture.yml on request.
-- `source` is what tells a real delivery from the demo seed;
-- identify_affected_components.yml says so when only demo rows are present.
--
-- Requires rpm_evr_functions.sql (the verdict functions at the end call it) and
-- inventory_catalog_schema.sql (they read installed_inventory).
-- This schema file creates empty tables and never seeds data.
-- identify_affected_components.yml refuses to run on an empty cache: zero
-- CVEs would report "clean" when it means "never looked".

-- ---------------------------------------------------------------------------
-- cve_events_received — local cache of CVEs delivered to this AAC instance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cve_events_received (
    cve_id                 varchar(50)  PRIMARY KEY,
    cvss_v3                numeric(3,1),
    severity               varchar(20),
    kev_member             boolean      DEFAULT false,
    published_at           timestamptz,
    vendor                 varchar(255),
    product                varchar(255),
    affected_versions      text[],
    affected_cpes          text[],
    description            text,
    cve_references         jsonb        DEFAULT '[]'::jsonb,
    suggested_playbook_ref varchar(255),
    source                 varchar(50),
    received_at            timestamptz  NOT NULL DEFAULT now(),
    source_event_payload   jsonb
);

CREATE INDEX IF NOT EXISTS idx_cve_severity_received
    ON cve_events_received (severity, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_cve_kev
    ON cve_events_received (kev_member) WHERE kev_member = true;
CREATE INDEX IF NOT EXISTS idx_cve_published
    ON cve_events_received (published_at DESC);

-- ---------------------------------------------------------------------------
-- cve_vendor_remediations — the published fix per (CVE, vendor), if any.
-- A CVE with no row here is still reported by the matcher (you are affected
-- whether or not a fix exists); it carries fix_match='none'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cve_vendor_remediations (
    id                  bigserial    PRIMARY KEY,
    cve_id              varchar(50)  NOT NULL REFERENCES cve_events_received(cve_id) ON DELETE CASCADE,
    vendor              varchar(255) NOT NULL,
    vendor_advisory_id  varchar(100),
    fix_version         varchar(100),
    patch_url           text,
    patch_description   text,
    available_at        timestamptz,
    received_at         timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (cve_id, vendor)
);

CREATE INDEX IF NOT EXISTS idx_vendor_rem_advisory
    ON cve_vendor_remediations (vendor_advisory_id) WHERE vendor_advisory_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- cve_fixed_builds — the build that fixes a CVE, PER PRODUCT STREAM.
-- cve_vendor_remediations holds one fix_version per (CVE, vendor); a vendor
-- that maintains several streams publishes one fixed build for each (a kernel
-- flaw is fixed in 5.14.0-687.64.1.el9_8 for RHEL 9 and in
-- 4.18.0-553.182.1.el8_10 for RHEL 8), and each is only comparable with an
-- installed build of the same stream.
--
--   fixed_evr    [epoch:]version-release of the fixed build; NULL when the
--                vendor states a position without a build (fix_state)
--   fix_state    fixed | not_affected | affected | will_not_fix | fix_deferred |
--                out_of_support | under_investigation
--   stream       product stream the row applies to: el8, el9, el10 …
--   dist_tag     the build's own dist tag (el9_8); an installed build with the
--                same tag is compared with THIS row before any other
--   base_os      true for the operating system's own repositories. Rows for a
--                layered product (OpenShift, a vendor kernel variant) are kept
--                for the record and NOT matched against hosts, because the
--                catalog cannot tell that a host runs that product.
--   source       who delivered the row (redhat_security_data_api, demo_seed …)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cve_fixed_builds (
    id            bigserial    PRIMARY KEY,
    cve_id        varchar(50)  NOT NULL REFERENCES cve_events_received(cve_id) ON DELETE CASCADE,
    package_name  varchar(255) NOT NULL,
    fixed_evr     varchar(255),
    fix_state     varchar(40)  NOT NULL DEFAULT 'fixed',
    stream        varchar(20),
    dist_tag      varchar(30),
    product_name  varchar(255) NOT NULL DEFAULT '',
    cpe           text,
    advisory_id   varchar(100),
    released_at   timestamptz,
    base_os       boolean      NOT NULL DEFAULT true,
    source        varchar(50)  NOT NULL,
    received_at   timestamptz  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cve_fixed_builds_identity
    ON cve_fixed_builds (cve_id, product_name, package_name, COALESCE(fixed_evr, ''));
CREATE INDEX IF NOT EXISTS idx_cve_fixed_builds_lookup
    ON cve_fixed_builds (cve_id, lower(package_name), stream);

-- ---------------------------------------------------------------------------
-- aac_cve_package_verdict — is ONE installed package affected by ONE CVE?
--
-- The single statement of the matching rule. identify_affected_components.yml
-- (through aac_cve_host_verdicts below) and patch_assurance.yml both call it.
--
--   verdict         meaning
--   affected        installed build is lower than the fixed build of its stream,
--                   or the vendor states the stream is affected with no build,
--                   or (no fixed build known) the version is in affected_versions
--   reboot_pending  the fixed build is INSTALLED but the host is still RUNNING a
--                   lower kernel build. Still affected.
--   fixed           installed (and, for a kernel, booted) build is at or above
--                   the fixed build of its stream
--   not_affected    the vendor states this stream is not affected
--   not_listed      no fixed build known; the CVE lists affected versions and
--                   this version is not among them
--   unknown         nothing to compare with: no fixed build for this stream and
--                   no affected-version list
--
-- Rules:
--   * rpm packages only are compared with a fixed build. Anything else falls
--     back to the exact affected_versions list.
--   * NEVER across streams. The host's stream is the dist tag of its installed
--     build (el9_8 -> el9), else p_os_stream. Fixed builds of other streams are
--     named in the detail and otherwise ignored.
--   * Within the stream, the row whose dist tag equals the installed build's
--     (an EUS / E4S branch such as el9_4) is used first; otherwise the highest
--     fixed build of the stream. A branch with no row of its own has no fix, so
--     the host has to reach the newest branch's build.
--   * Module-stream builds (release contains ".module+") are not evaluated.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_cve_package_verdict(
    p_cve_id            text,
    p_package           text,
    p_format            text,
    p_installed_evr     text,
    p_booted_evr        text,
    p_os_stream         text,
    p_installed_version text,
    p_affected_versions text[]
) RETURNS TABLE (verdict text, fixed_evr text, advisory_id text, basis text, detail text)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
DECLARE
    v_stream   text;
    v_tag      text;
    v_best     text;
    v_best_adv text;
    v_exact    boolean := false;
    v_state    record;
    v_others   text;
    v_modular  boolean := false;
    r          record;
BEGIN
    IF p_format = 'rpm' AND p_installed_evr IS NOT NULL THEN
        v_tag    := aac_rpm_dist_tag(p_installed_evr);
        v_stream := COALESCE(aac_rpm_stream(p_installed_evr), NULLIF(p_os_stream, ''));

        FOR r IN
            SELECT f.fixed_evr, f.advisory_id, f.dist_tag
              FROM cve_fixed_builds f
             WHERE f.cve_id = p_cve_id
               AND lower(f.package_name) = lower(p_package)
               AND f.base_os
               AND f.fix_state = 'fixed'
               AND f.fixed_evr IS NOT NULL
               AND f.stream IS NOT DISTINCT FROM v_stream
        LOOP
            IF r.fixed_evr LIKE '%.module+%' THEN
                v_modular := true;
                CONTINUE;
            END IF;
            IF v_tag IS NOT NULL AND r.dist_tag = v_tag THEN
                IF NOT v_exact OR aac_evr_cmp(r.fixed_evr, v_best) > 0 THEN
                    v_best     := r.fixed_evr;
                    v_best_adv := r.advisory_id;
                END IF;
                v_exact := true;
            ELSIF NOT v_exact
                  AND (v_best IS NULL OR aac_evr_cmp(r.fixed_evr, v_best) > 0) THEN
                v_best     := r.fixed_evr;
                v_best_adv := r.advisory_id;
            END IF;
        END LOOP;

        IF v_best IS NOT NULL THEN
            fixed_evr   := v_best;
            advisory_id := v_best_adv;
            basis       := 'fixed_build';
            IF aac_evr_cmp(p_installed_evr, v_best) < 0 THEN
                verdict := 'affected';
                detail  := format('installed %s is lower than the fixed build %s (%s)',
                                  p_installed_evr, v_best, COALESCE(v_stream, 'no stream'));
                IF p_booted_evr IS NOT NULL THEN
                    detail := detail || format('; booted %s', p_booted_evr);
                END IF;
            ELSIF p_booted_evr IS NOT NULL AND aac_evr_cmp(p_booted_evr, v_best) < 0 THEN
                verdict := 'reboot_pending';
                detail  := format('fixed build installed, reboot pending: installed %s, booted %s, fixed build %s (%s)',
                                  p_installed_evr, p_booted_evr, v_best, COALESCE(v_stream, 'no stream'));
            ELSE
                verdict := 'fixed';
                detail  := format('installed %s is at or above the fixed build %s (%s)',
                                  p_installed_evr, v_best, COALESCE(v_stream, 'no stream'));
                IF p_booted_evr IS NOT NULL THEN
                    detail := detail || format('; booted %s', p_booted_evr);
                END IF;
            END IF;
            RETURN NEXT;
            RETURN;
        END IF;

        -- No fixed build for this stream. Does the vendor state a position?
        SELECT f.fix_state, f.product_name INTO v_state
          FROM cve_fixed_builds f
         WHERE f.cve_id = p_cve_id
           AND lower(f.package_name) = lower(p_package)
           AND f.base_os
           AND f.fix_state <> 'fixed'
           AND f.stream IS NOT DISTINCT FROM v_stream
         ORDER BY (f.fix_state = 'not_affected') ASC, f.id ASC
         LIMIT 1;
        IF FOUND THEN
            basis   := 'vendor_state';
            verdict := CASE
                         WHEN v_state.fix_state = 'not_affected' THEN 'not_affected'
                         WHEN v_state.fix_state IN ('affected', 'will_not_fix', 'fix_deferred') THEN 'affected'
                         ELSE 'unknown'
                       END;
            detail  := format('vendor state for %s (%s): %s; no fixed build published',
                              COALESCE(NULLIF(v_state.product_name, ''), 'this stream'),
                              COALESCE(v_stream, 'no stream'), v_state.fix_state);
            RETURN NEXT;
            RETURN;
        END IF;

        -- Fixed builds exist, but only for other streams (or only as module
        -- builds): say so and do not compare.
        SELECT string_agg(DISTINCT COALESCE(f.stream, 'no stream'), ', '
                          ORDER BY COALESCE(f.stream, 'no stream')) INTO v_others
          FROM cve_fixed_builds f
         WHERE f.cve_id = p_cve_id
           AND lower(f.package_name) = lower(p_package)
           AND f.base_os
           AND f.fixed_evr IS NOT NULL;
        IF v_others IS NOT NULL THEN
            verdict := 'unknown';
            basis   := 'no_build_for_stream';
            detail  := CASE WHEN v_modular
                         THEN format('the fixed build for %s is a module-stream build, which is not evaluated',
                                     COALESCE(v_stream, 'this host'))
                         ELSE format('no fixed build published for stream %s (fixed builds exist for: %s); '
                                     'builds of another stream are not comparable',
                                     COALESCE(v_stream, 'unknown'), v_others)
                       END;
            RETURN NEXT;
            RETURN;
        END IF;
    END IF;

    -- Fallback: the exact affected-version list, as before fixed builds existed.
    basis := 'affected_versions';
    IF p_affected_versions IS NULL OR cardinality(p_affected_versions) = 0 THEN
        verdict := 'unknown';
        detail  := 'no fixed build and no affected-version list for this CVE';
    ELSIF p_installed_version = ANY (p_affected_versions) THEN
        verdict := 'affected';
        detail  := format('installed version %s is in the affected-version list', p_installed_version);
    ELSE
        verdict := 'not_listed';
        detail  := format('installed version %s is not in the affected-version list', p_installed_version);
    END IF;
    RETURN NEXT;
END;
$$;

-- ---------------------------------------------------------------------------
-- aac_cve_host_verdicts(filter) — every CVE in scope against every observed
-- host. `filter` is a comma-separated list of CVE ids, or '' for all.
--
-- One row per matched installed component, plus ONE row with
-- verdict='not_installed' for each (CVE, host) where no component matched:
-- "not affected (not installed)" is an answer, and a different one from
-- 'unknown'. Nothing is stored; identify_affected_components.yml inserts the
-- affected / reboot_pending / unknown rows into patch_worklist and prints the
-- counts of the rest.
--
-- A component matches a CVE by CPE, by the CVE's product name, or by the
-- package name of one of its base-OS fixed builds (a kernel CVE names both
-- kernel and kernel-rt). Advisories name the kernel by its `kernel` package; a
-- host that carries kernel-core without the `kernel` meta package (minimal and
-- cloud images) is matched on kernel-core against the same fixed build, so it
-- is not reported as "not installed", and a kernel-rt built from the kernel
-- source (RHEL 9 and later) is judged against the `kernel` rows.
--
-- LIMIT: apart from that kernel handling, a component is matched on the
-- package name the advisory gives (usually the source package). A host that
-- carries only a differently named subpackage (openssl-libs without openssl)
-- is not matched; the catalog does not hold the source rpm of each package.
--
-- Exactly one remediation per matched component: the vendor that ships THIS
-- installed package first, then the CVE's own vendor, then the earliest
-- published fix (cve_vendor_remediations is keyed (cve_id, vendor), so a plain
-- join would multiply rows).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_cve_host_verdicts(p_filter text DEFAULT '')
RETURNS TABLE (
    cve_id            text,
    severity          text,
    kev_member        boolean,
    hostname          text,
    os_family         text,
    vendor            text,
    product           text,
    installed_version text,
    installed_evr     text,
    booted_evr        text,
    fixed_evr         text,
    fix_version       text,
    fix_vendor        text,
    advisory_id       text,
    patch_url         text,
    match_kind        text,
    verdict           text,
    basis             text,
    detail            text
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    WITH scope AS (
        SELECT c.cve_id, c.severity, c.kev_member, c.vendor, c.product,
               c.affected_versions, c.affected_cpes
          FROM cve_events_received c
         WHERE COALESCE(p_filter, '') = ''
            OR c.cve_id = ANY (string_to_array(replace(p_filter, ' ', ''), ','))
    ),
    targets AS (
        SELECT s.cve_id, lower(s.product) AS package FROM scope s WHERE s.product IS NOT NULL
        UNION
        SELECT f.cve_id, lower(f.package_name)
          FROM cve_fixed_builds f JOIN scope s ON s.cve_id = f.cve_id
         WHERE f.base_os
    ),
    -- Candidates first, verdicts second: the verdict function runs only for
    -- the components that match a CVE, not for the whole CVE x inventory product.
    cand AS MATERIALIZED (
        SELECT c.cve_id, c.severity, c.kev_member, c.vendor AS cve_vendor,
               c.product AS cve_product, c.affected_versions, c.affected_cpes,
               i.hostname, i.os_family, i.os_version, i.package_name, i.package_vendor,
               i.package_version, i.package_format, i.package_evr, i.booted_evr, i.cpe,
               lk.name AS advisory_name
          FROM scope c
          JOIN installed_inventory i ON true
          -- The name the advisory uses for this installed package.
          CROSS JOIN LATERAL (
              SELECT CASE
                       -- RHEL 9 and later build kernel-rt from the kernel source
                       -- (same version-release) and advisories list only `kernel`.
                       -- RHEL 8 kernel-rt has its own build (…rt7.N…) and its own rows.
                       WHEN lower(i.package_name) ~ '^kernel-rt(-core)?$'
                            AND COALESCE(i.package_evr, '') !~ '[.]rt[0-9]+[.]'  THEN 'kernel'
                       WHEN lower(i.package_name) ~ '^kernel(-rt)?-core$'
                            THEN regexp_replace(lower(i.package_name), '-core$', '')
                       ELSE lower(i.package_name)
                     END AS name
          ) lk
         WHERE (i.cpe IS NOT NULL AND c.affected_cpes IS NOT NULL
                AND i.cpe = ANY (c.affected_cpes))
            OR (EXISTS (SELECT 1 FROM targets t
                         WHERE t.cve_id = c.cve_id AND t.package IN (lower(i.package_name), lk.name))
                -- kernel-core stands in for `kernel` only where the meta
                -- package is absent; otherwise one host would carry two work
                -- items for one kernel.
                AND NOT (lower(i.package_name) ~ '^kernel(-rt)?-core$'
                         AND EXISTS (SELECT 1 FROM installed_inventory k
                                      WHERE k.hostname = i.hostname
                                        AND k.package_format = 'rpm'
                                        AND lower(k.package_name)
                                            = regexp_replace(lower(i.package_name), '-core$', ''))))
    ),
    matched AS (
        SELECT
            x.cve_id, x.severity,
            COALESCE(x.kev_member, false)                           AS kev_member,
            x.hostname, x.os_family,
            COALESCE(NULLIF(x.package_vendor, ''), x.cve_vendor)    AS vendor,
            x.package_name                                          AS product,
            x.package_version                                       AS installed_version,
            x.package_evr                                           AS installed_evr,
            x.booted_evr,
            v.fixed_evr,
            r.fix_version, r.fix_vendor,
            COALESCE(v.advisory_id, r.vendor_advisory_id)           AS advisory_id,
            r.patch_url,
            CASE
              WHEN x.cpe IS NOT NULL AND x.affected_cpes IS NOT NULL
                   AND x.cpe = ANY (x.affected_cpes)                       THEN 'cpe'
              WHEN lower(COALESCE(x.package_vendor, '')) = lower(COALESCE(x.cve_vendor, ''))
                   AND lower(x.package_name) = lower(x.cve_product)        THEN 'vendor_product'
              ELSE 'product'
            END                                                     AS match_kind,
            v.verdict, v.basis, v.detail
          FROM cand x
          CROSS JOIN LATERAL aac_cve_package_verdict(
                x.cve_id, x.advisory_name,
                x.package_format, x.package_evr, x.booted_evr,
                CASE WHEN x.os_family ~* 'red ?hat' AND x.os_version ~ '^[0-9]+'
                     THEN 'el' || substring(x.os_version FROM '^[0-9]+') END,
                x.package_version, x.affected_versions) v
          -- Exactly one remediation per matched component. LIMIT 1 is the guarantee.
          LEFT JOIN LATERAL (
              SELECT r.fix_version, r.vendor AS fix_vendor, r.vendor_advisory_id,
                     r.patch_url, r.available_at
                FROM cve_vendor_remediations r
               WHERE r.cve_id = x.cve_id
               ORDER BY (lower(r.vendor) = lower(COALESCE(NULLIF(x.package_vendor, ''), x.cve_vendor, ''))) DESC,
                        (lower(r.vendor) = lower(COALESCE(x.cve_vendor, ''))) DESC,
                        r.available_at ASC NULLS LAST,
                        r.id ASC
               LIMIT 1
          ) r ON true
    ),
    hosts AS (
        SELECT i.hostname, max(i.os_family) AS os_family
          FROM installed_inventory i
         GROUP BY i.hostname
    )
    SELECT m.cve_id::text, m.severity::text, m.kev_member, m.hostname::text, m.os_family::text,
           m.vendor::text, m.product::text, m.installed_version::text, m.installed_evr::text,
           m.booted_evr::text, m.fixed_evr, m.fix_version::text, m.fix_vendor::text,
           m.advisory_id::text, m.patch_url, m.match_kind, m.verdict, m.basis, m.detail
      FROM matched m
    UNION ALL
    SELECT c.cve_id::text, c.severity::text, COALESCE(c.kev_member, false), h.hostname::text,
           h.os_family::text, c.vendor::text, c.product::text,
           NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
           'not_installed', 'inventory',
           'not affected (not installed): no matching component in this host''s inventory'
      FROM scope c
     CROSS JOIN hosts h
     WHERE NOT EXISTS (SELECT 1 FROM matched m
                        WHERE m.cve_id = c.cve_id AND m.hostname = h.hostname);
END;
$$;

-- Read-only access for the reporting role, mirroring inventory_catalog_schema.sql.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_reader') THEN
        GRANT SELECT ON cve_events_received, cve_vendor_remediations, cve_fixed_builds TO compliance_reader;
    END IF;
END
$$;
