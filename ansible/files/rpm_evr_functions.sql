-- rpm_evr_functions.sql — rpm version comparison for the patch-intelligence playbooks
--
-- ONE implementation of rpm's ordering, in the database, because that is where
-- the matching happens: refresh_inventory_catalog.yml picks the newest installed
-- build with it, cve_cache_schema.sql (aac_cve_package_verdict) decides
-- "installed is lower than the fixed build" with it, and patch_assurance.yml and
-- patch_closure_verify.sql call the same functions. Tested by
-- tests/test_rpm_evr_functions.py against a real PostgreSQL.
--
-- Idempotent: every statement is CREATE OR REPLACE. No tables, no data.
-- Apply BEFORE inventory_catalog_schema.sql and cve_cache_schema.sql.
--
-- An EVR is written  [epoch:]version[-release] . A missing epoch is 0.

-- ---------------------------------------------------------------------------
-- aac_rpmvercmp(a, b) -> -1 | 0 | 1
-- rpm's rpmvercmp(): compare two version (or two release) strings segment by
-- segment. Segments are runs of digits or runs of ASCII letters; every other
-- character only separates. A numeric segment is newer than an alphabetic one,
-- numeric segments compare as numbers (so 1.10 is newer than 1.9), alphabetic
-- ones as bytes. '~' sorts before everything, including the end of the string
-- (1.0~rc1 is older than 1.0); '^' sorts after the end of the string but before
-- any further segment (1.0^git1 is newer than 1.0, older than 1.0.1).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_rpmvercmp(a text, b text) RETURNS integer
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    one   text := a;
    two   text := b;
    seg1  text;
    seg2  text;
    isnum boolean;
BEGIN
    IF one = two THEN
        RETURN 0;
    END IF;
    LOOP
        one := regexp_replace(one, '^[^A-Za-z0-9~^]+', '');
        two := regexp_replace(two, '^[^A-Za-z0-9~^]+', '');
        EXIT WHEN one = '' AND two = '';

        IF left(one, 1) = '~' OR left(two, 1) = '~' THEN
            IF left(one, 1) <> '~' OR one = '' THEN RETURN 1; END IF;
            IF left(two, 1) <> '~' OR two = '' THEN RETURN -1; END IF;
            one := substr(one, 2);
            two := substr(two, 2);
            CONTINUE;
        END IF;

        IF left(one, 1) = '^' OR left(two, 1) = '^' THEN
            IF one = '' THEN RETURN -1; END IF;
            IF two = '' THEN RETURN 1; END IF;
            IF left(one, 1) <> '^' THEN RETURN 1; END IF;
            IF left(two, 1) <> '^' THEN RETURN -1; END IF;
            one := substr(one, 2);
            two := substr(two, 2);
            CONTINUE;
        END IF;

        EXIT WHEN one = '' OR two = '';

        isnum := left(one, 1) BETWEEN '0' AND '9';
        IF isnum THEN
            seg1 := substring(one FROM '^[0-9]+');
            seg2 := COALESCE(substring(two FROM '^[0-9]+'), '');
        ELSE
            seg1 := substring(one FROM '^[A-Za-z]+');
            seg2 := COALESCE(substring(two FROM '^[A-Za-z]+'), '');
        END IF;
        -- The segments are of different types: the numeric one is newer.
        IF seg2 = '' THEN
            RETURN CASE WHEN isnum THEN 1 ELSE -1 END;
        END IF;
        one := substr(one, length(seg1) + 1);
        two := substr(two, length(seg2) + 1);

        IF isnum THEN
            seg1 := regexp_replace(seg1, '^0+', '');
            seg2 := regexp_replace(seg2, '^0+', '');
            IF length(seg1) > length(seg2) THEN RETURN 1; END IF;
            IF length(seg2) > length(seg1) THEN RETURN -1; END IF;
        END IF;
        IF seg1 COLLATE "C" < seg2 COLLATE "C" THEN RETURN -1; END IF;
        IF seg1 COLLATE "C" > seg2 COLLATE "C" THEN RETURN 1; END IF;
    END LOOP;

    IF one = '' AND two = '' THEN RETURN 0; END IF;
    -- Whichever string still has segments left is newer.
    RETURN CASE WHEN one = '' THEN -1 ELSE 1 END;
END;
$$;

-- ---------------------------------------------------------------------------
-- aac_evr(epoch, version, release) -> '[epoch:]version[-release]'
-- The canonical text form stored in installed_inventory.package_evr. A missing
-- or zero epoch is left out, so the string is what `dnf install name-<evr>` and
-- `rpm -q` print.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_evr(epoch text, version text, release text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN version IS NULL OR version = '' THEN NULL ELSE
           CASE WHEN COALESCE(epoch, '') ~ '^[0-9]+$' AND epoch::numeric <> 0
                THEN (epoch::numeric)::text || ':' ELSE '' END
           || version
           || CASE WHEN COALESCE(release, '') <> '' THEN '-' || release ELSE '' END
           END
$$;

-- aac_evr_epoch / aac_evr_version / aac_evr_release — the three parts of an EVR.
CREATE OR REPLACE FUNCTION aac_evr_epoch(evr text) RETURNS numeric
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT COALESCE(substring(evr FROM '^([0-9]+):')::numeric, 0)
$$;

CREATE OR REPLACE FUNCTION aac_evr_version(evr text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT regexp_replace(regexp_replace(evr, '^[0-9]+:', ''), '-[^-]*$', '')
$$;

CREATE OR REPLACE FUNCTION aac_evr_release(evr text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT substring(regexp_replace(evr, '^[0-9]+:', '') FROM '-([^-]*)$')
$$;

-- ---------------------------------------------------------------------------
-- aac_evr_cmp(a, b) -> -1 | 0 | 1
-- Epoch first (as a number), then version, then release, each with
-- aac_rpmvercmp. When EITHER side has no release the releases are not compared
-- (rpm's own rule for a dependency written without one), so a version-only fix
-- such as '3.2.4' is satisfied by any installed 3.2.4-<release>.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_evr_cmp(a text, b text) RETURNS integer
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    ea numeric := aac_evr_epoch(a);
    eb numeric := aac_evr_epoch(b);
    ra text := aac_evr_release(a);
    rb text := aac_evr_release(b);
    rc integer;
BEGIN
    IF ea < eb THEN RETURN -1; END IF;
    IF ea > eb THEN RETURN 1; END IF;
    rc := aac_rpmvercmp(aac_evr_version(a), aac_evr_version(b));
    IF rc <> 0 THEN RETURN rc; END IF;
    IF COALESCE(ra, '') = '' OR COALESCE(rb, '') = '' THEN RETURN 0; END IF;
    RETURN aac_rpmvercmp(ra, rb);
END;
$$;

-- aac_evr_max(evrs) — the newest EVR in an array (NULL for an empty array).
-- A host keeps several kernels installed; the catalog records the newest.
CREATE OR REPLACE FUNCTION aac_evr_max(evrs text[]) RETURNS text
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE
    best text;
    e    text;
BEGIN
    IF evrs IS NULL THEN RETURN NULL; END IF;
    FOREACH e IN ARRAY evrs LOOP
        IF e IS NOT NULL AND (best IS NULL OR aac_evr_cmp(e, best) > 0) THEN
            best := e;
        END IF;
    END LOOP;
    RETURN best;
END;
$$;

-- ---------------------------------------------------------------------------
-- Product stream. A fixed build is only comparable with an installed build of
-- the SAME stream: 4.18.0-553.182.1.el8_10 says nothing about an el9 host.
--   aac_rpm_dist_tag('5.14.0-687.64.1.el9_8') -> 'el9_8'
--   aac_rpm_stream('5.14.0-687.64.1.el9_8')   -> 'el9'
-- NULL when the release carries no recognised dist tag.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_rpm_dist_tag(evr text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT substring(COALESCE(aac_evr_release(evr), evr)
                     FROM '(?:^|[.+])((?:el|fc|amzn|sle|oe)[0-9]+(?:_[0-9]+)?)(?![0-9])')
$$;

CREATE OR REPLACE FUNCTION aac_rpm_stream(evr text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT substring(aac_rpm_dist_tag(evr) FROM '^[a-z]+[0-9]+')
$$;

-- ---------------------------------------------------------------------------
-- Booted kernel. `uname -r` (ansible_kernel) is the release of the RUNNING
-- kernel, which is not the newest installed one until the host reboots.
--   aac_kernel_booted_evr('5.14.0-687.61.1.el9_8.x86_64')     -> '5.14.0-687.61.1.el9_8'
--   aac_kernel_booted_evr('5.14.0-687.61.1.el9_8.x86_64+rt')  -> '5.14.0-687.61.1.el9_8'
--   aac_kernel_flavour('5.14.0-687.61.1.el9_8.x86_64+rt')     -> 'rt'
--   aac_kernel_flavour('4.18.0-553.182.1.rt7.523.el8_10.x86_64') -> 'rt'
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION aac_kernel_booted_evr(uname_r text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT NULLIF(regexp_replace(
               regexp_replace(btrim(uname_r), '\+[A-Za-z0-9_-]+$', ''),
               '\.(x86_64|aarch64|ppc64le|ppc64|s390x|i686|i386|armv7hl|riscv64|noarch)$', ''), '')
$$;

CREATE OR REPLACE FUNCTION aac_kernel_flavour(uname_r text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE
             WHEN btrim(uname_r) ~ '\+[A-Za-z0-9_-]+$'
                  THEN substring(btrim(uname_r) FROM '\+([A-Za-z0-9_-]+)$')
             WHEN uname_r ~ '\.rt[0-9]+\.' THEN 'rt'
             ELSE ''
           END
$$;

-- aac_kernel_booted_evr_for(package, uname -r) — the booted EVR when `package`
-- is one of the packages that carry the RUNNING kernel image (kernel,
-- kernel-core, kernel-modules…, or kernel-rt… on a realtime kernel), else NULL.
-- kernel-headers, kernel-tools and the like are userland: for those the
-- installed build is the whole answer and no booted build is recorded.
CREATE OR REPLACE FUNCTION aac_kernel_booted_evr_for(package_name text, uname_r text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE
             WHEN uname_r !~ '^[0-9]+\.[0-9]+' THEN NULL
             WHEN lower(package_name) ~ ('^kernel'
                    || CASE WHEN aac_kernel_flavour(uname_r) = '' THEN ''
                            ELSE '-' || regexp_replace(aac_kernel_flavour(uname_r), '[^a-z0-9-]', '', 'g') END
                    || '(-core|-modules|-modules-core|-modules-extra)?$')
                  THEN aac_kernel_booted_evr(uname_r)
             ELSE NULL
           END
$$;
