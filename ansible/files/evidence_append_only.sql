-- evidence_append_only.sql — make the evidence store append-only and tamper-evident
--
-- Applied by aac_compliance_db (tasks/schema.yml) on every install and re-run;
-- every statement is idempotent. See docs/EVIDENCE_IMMUTABILITY.md.
--
-- WHAT THIS ENFORCES
-- ------------------
-- 1. compliance_results and compliance_certifications refuse UPDATE and DELETE
--    at the database. A verdict, once written, is never rewritten.
-- 2. Every compliance_results row carries a hash chain: row_hash is the SHA-256
--    of the row's content plus the previous row's hash, in chain_seq order (an
--    ordinal allocated inside the chain lock, since SERIAL ids are not). Rewriting any row, even
--    by a superuser who drops the guard, breaks the chain from that row forward,
--    and evidence_chain_verify() says where.
-- 3. The only sanctioned way to change history is the maintenance path: a
--    session sets aac.evidence_maintenance = 'on' AND a non-empty
--    aac.evidence_maintenance_note; every UPDATE/DELETE is then recorded in
--    evidence_maintenance_log with the complete old row, and the
--    chain still breaks so the change stays visible to the verifier.
-- 4. Corrections are new rows. compliance_results.supersedes points at the row
--    a correction replaces; compliance_results_current hides superseded rows.
--
-- WHAT IT DOES NOT PROTECT AGAINST
-- --------------------------------
-- A superuser or the table owner can drop these triggers. That is why the
-- assessment playbooks should write as the compliance_writer role (INSERT and
-- SELECT only, created by aac_compliance_db), why the chain exists at all, and
-- why verify_evidence_chain.yml publishes the chain head as an AAP job artifact:
-- the anchor lives outside the database.

SET client_min_messages = warning;

-- ---------------------------------------------------------------------------
-- 0. Columns (additive, guarded for pre-existing installs)
-- ---------------------------------------------------------------------------
-- Provenance columns (same definitions as evidence_provenance.sql). A fresh
-- install reaches this file before fix_evidence_integrity.yml has ever run,
-- and aac_store_results already INSERTs into both, so they belong here too.
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS policy_sha  VARCHAR(64);
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS project_sha VARCHAR(64);
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS supersedes INTEGER REFERENCES compliance_results(id);
-- Chain ordinal: allocated INSIDE the advisory lock by the insert trigger, so chain
-- order and ordinal order can never disagree. The SERIAL id is allocated by the
-- column default BEFORE any trigger runs and so cannot serve as the chain order.
CREATE SEQUENCE IF NOT EXISTS compliance_results_chain_seq;
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS chain_seq  BIGINT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_results_chain_seq ON compliance_results(chain_seq) WHERE chain_seq IS NOT NULL;
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS prev_hash  CHAR(64);
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS row_hash   CHAR(64);
CREATE INDEX IF NOT EXISTS idx_results_supersedes ON compliance_results(supersedes) WHERE supersedes IS NOT NULL;

COMMENT ON COLUMN compliance_results.supersedes IS
  'Correction protocol: this row replaces the row with this id. The old row stays; '
  'compliance_results_current hides it.';
COMMENT ON COLUMN compliance_results.chain_seq IS
  'Position in the hash chain, allocated inside the chain lock. Verification walks this order, not id.';
COMMENT ON COLUMN compliance_results.row_hash IS
  'SHA-256 over evidence_row_canonical(row), which includes prev_hash and chain_seq. Set by trigger; '
  'verify with evidence_chain_verify().';

-- ---------------------------------------------------------------------------
-- 1. Maintenance log — the audit trail of the only sanctioned rewrite path.
--    Append-only itself, with no maintenance escape.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_maintenance_log (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    db_user     TEXT         NOT NULL DEFAULT current_user,
    client_addr INET         DEFAULT inet_client_addr(),
    operation   TEXT         NOT NULL,          -- UPDATE | DELETE
    table_name  TEXT         NOT NULL,
    row_key     TEXT         NOT NULL,          -- id or certification_id of the touched row
    old_row     JSONB        NOT NULL,          -- the complete row before the change
    note        TEXT                            -- aac.evidence_maintenance_note, if the session set one
);
COMMENT ON TABLE evidence_maintenance_log IS
  'Every UPDATE/DELETE that the evidence guard let through under aac.evidence_maintenance=on, '
  'with the full old row. Append-only; nothing can clear it short of dropping the trigger.';

CREATE OR REPLACE FUNCTION evidence_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'evidence_maintenance_log is append-only (% blocked)', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_evidence_log_append_only ON evidence_maintenance_log;
CREATE TRIGGER trg_evidence_log_append_only
    BEFORE UPDATE OR DELETE ON evidence_maintenance_log
    FOR EACH ROW EXECUTE FUNCTION evidence_log_append_only();

-- ---------------------------------------------------------------------------
-- 2. The guard: refuse UPDATE/DELETE unless the session declared maintenance,
--    and in that case record the old row first.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION evidence_append_only_guard() RETURNS trigger AS $$
DECLARE
    v_key  TEXT;
    v_note TEXT;
BEGIN
    -- The one sanctioned in-place write that is not a rewrite: linking an old
    -- certification to its successor. Allowed only when superseded_by goes from
    -- NULL to a value and NOTHING else in the row changes.
    IF TG_TABLE_NAME = 'compliance_certifications' AND TG_OP = 'UPDATE'
       AND (to_jsonb(OLD) ->> 'superseded_by') IS NULL
       AND (to_jsonb(NEW) ->> 'superseded_by') IS NOT NULL
       AND (to_jsonb(OLD) - 'superseded_by') = (to_jsonb(NEW) - 'superseded_by') THEN
        RETURN NEW;
    END IF;

    IF COALESCE(current_setting('aac.evidence_maintenance', true), '') <> 'on' THEN
        RAISE EXCEPTION '% is append-only: % refused. Corrections are new rows (supersedes = old id). '
                        'Deliberate maintenance must SET aac.evidence_maintenance = ''on'' and is logged.',
                        TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    v_note := NULLIF(btrim(COALESCE(current_setting('aac.evidence_maintenance_note', true), '')), '');
    IF v_note IS NULL THEN
        RAISE EXCEPTION 'evidence maintenance on % requires a reason: SET aac.evidence_maintenance_note = ''<why, by whom, ticket>''',
                        TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    v_key := COALESCE(
        (to_jsonb(OLD) ->> 'id'),
        (to_jsonb(OLD) ->> 'certification_id'),
        '?');

    INSERT INTO evidence_maintenance_log (operation, table_name, row_key, old_row, note)
    VALUES (TG_OP, TG_TABLE_NAME, v_key, to_jsonb(OLD), v_note);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 3. Canonical form and hash chain for compliance_results.
--    The canonical text covers every evidence column (prev_hash included, row_hash
--    excluded) with explicit NULL markers, so NULL and empty are distinguishable.
--    NOTE: evidence_row_canonical() is a public contract. Changing it invalidates
--    every existing hash; if a column must be added, add it at the END and
--    re-anchor with a documented maintenance run.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION evidence_row_canonical(r compliance_results) RETURNS text AS $$
    SELECT concat_ws(E'\x1f',
        'aac-evidence-v1',
        COALESCE(r.prev_hash, '<null>'),
        COALESCE(r.id::text, '<null>'),
        COALESCE(r.chain_seq::text, '<null>'),
        COALESCE(r.hostname, '<null>'),
        COALESCE(r.ip_address, '<null>'),
        COALESCE(r.framework, '<null>'),
        COALESCE(r.policy_name, '<null>'),
        COALESCE(r.policy_version, '<null>'),
        COALESCE(r.total_controls::text, '<null>'),
        COALESCE(r.passed_controls::text, '<null>'),
        COALESCE(r.failed_controls::text, '<null>'),
        COALESCE(r.compliance_percentage::text, '<null>'),
        COALESCE(r.compliant::text, '<null>'),
        COALESCE(r.violations::text, '<null>'),
        COALESCE(r.metadata::text, '<null>'),
        COALESCE(to_char(r.evaluation_timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.US'), '<null>'),
        COALESCE(r.facts_id::text, '<null>'),
        COALESCE(r.policy_sha, '<null>'),
        COALESCE(r.project_sha, '<null>'),
        COALESCE(r.supersedes::text, '<null>')
    )
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION evidence_hash(canonical text) RETURNS char(64) AS $$
    SELECT encode(sha256(convert_to(canonical, 'UTF8')), 'hex')::char(64)
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION evidence_chain_genesis() RETURNS char(64) AS $$
    SELECT repeat('0', 64)::char(64)
$$ LANGUAGE sql IMMUTABLE;

-- BEFORE INSERT: serialise writers, link to the chain head, hash the row.
-- Column defaults (id, evaluation_timestamp) are already applied when this runs.
CREATE OR REPLACE FUNCTION evidence_chain_link() RETURNS trigger AS $$
DECLARE
    v_prev CHAR(64);
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('compliance_results_chain'));
    SELECT row_hash INTO v_prev
      FROM compliance_results
     WHERE chain_seq IS NOT NULL
     ORDER BY chain_seq DESC
     LIMIT 1;
    NEW.chain_seq := nextval('compliance_results_chain_seq');
    NEW.prev_hash := COALESCE(v_prev, evidence_chain_genesis());
    NEW.row_hash  := evidence_hash(evidence_row_canonical(NEW));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 4. Anchor rows that predate the chain. Runs once per row (row_hash IS NULL),
--    in id order, under the maintenance setting so the guard logs each row.
--    Hashes are integrity metadata; no verdict content is touched.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r      compliance_results%ROWTYPE;
    v_prev CHAR(64);
    n      INTEGER := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM compliance_results WHERE row_hash IS NULL OR chain_seq IS NULL) THEN
        RETURN;
    END IF;
    PERFORM set_config('aac.evidence_maintenance', 'on', true);
    PERFORM set_config('aac.evidence_maintenance_note',
                       'evidence_append_only.sql: anchoring rows that predate the hash chain', true);
    PERFORM pg_advisory_xact_lock(hashtext('compliance_results_chain'));
    SELECT row_hash INTO v_prev FROM compliance_results
     WHERE chain_seq IS NOT NULL ORDER BY chain_seq DESC LIMIT 1;
    v_prev := COALESCE(v_prev, evidence_chain_genesis());
    FOR r IN SELECT * FROM compliance_results WHERE row_hash IS NULL OR chain_seq IS NULL ORDER BY id LOOP
        r.chain_seq := nextval('compliance_results_chain_seq');
        r.prev_hash := v_prev;
        r.row_hash  := evidence_hash(evidence_row_canonical(r));
        UPDATE compliance_results
           SET chain_seq = r.chain_seq, prev_hash = r.prev_hash, row_hash = r.row_hash
         WHERE id = r.id;
        v_prev := r.row_hash;
        n := n + 1;
    END LOOP;
    RAISE NOTICE 'evidence chain: anchored % pre-existing rows', n;
END $$;

-- ---------------------------------------------------------------------------
-- 5. Triggers (dropped and recreated so re-runs converge)
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_compliance_results_chain ON compliance_results;
CREATE TRIGGER trg_compliance_results_chain
    BEFORE INSERT ON compliance_results
    FOR EACH ROW EXECUTE FUNCTION evidence_chain_link();

DROP TRIGGER IF EXISTS trg_compliance_results_append_only ON compliance_results;
CREATE TRIGGER trg_compliance_results_append_only
    BEFORE UPDATE OR DELETE ON compliance_results
    FOR EACH ROW EXECUTE FUNCTION evidence_append_only_guard();

DROP TRIGGER IF EXISTS trg_compliance_certifications_append_only ON compliance_certifications;
CREATE TRIGGER trg_compliance_certifications_append_only
    BEFORE UPDATE OR DELETE ON compliance_certifications
    FOR EACH ROW EXECUTE FUNCTION evidence_append_only_guard();

-- ---------------------------------------------------------------------------
-- 6. Current view: the correction protocol's reading side.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW compliance_results_current AS
SELECT c.*
  FROM compliance_results c
 WHERE NOT EXISTS (SELECT 1 FROM compliance_results s WHERE s.supersedes = c.id);
COMMENT ON VIEW compliance_results_current IS
  'compliance_results minus rows that a later correction row supersedes. Read this for posture; '
  'read the table for history.';

-- ---------------------------------------------------------------------------
-- 7. Verifier: walk the chain in id order and recompute every link.
--    One row of counts; first_break_id is NULL when the chain is intact.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION evidence_chain_verify()
RETURNS TABLE (
    total_rows     BIGINT,
    chained_rows   BIGINT,
    unhashed_rows  BIGINT,
    broken_rows    BIGINT,
    first_break_id INTEGER,
    head_id        INTEGER,
    head_hash      CHAR(64),
    guard_present  BOOLEAN
) AS $$
DECLARE
    r        compliance_results%ROWTYPE;
    v_prev   CHAR(64) := evidence_chain_genesis();
    v_expect CHAR(64);
BEGIN
    total_rows := 0; chained_rows := 0; unhashed_rows := 0; broken_rows := 0;
    first_break_id := NULL; head_id := NULL; head_hash := NULL;

    -- Unhashed rows come first (NULLS FIRST) so they are reported, and they count
    -- as breaks: after anchoring, a row outside the chain is an anomaly, not a gap.
    FOR r IN SELECT * FROM compliance_results ORDER BY chain_seq NULLS FIRST, id LOOP
        total_rows := total_rows + 1;
        IF r.row_hash IS NULL OR r.chain_seq IS NULL THEN
            unhashed_rows := unhashed_rows + 1;
            broken_rows   := broken_rows + 1;
            IF first_break_id IS NULL THEN
                first_break_id := r.id;
            END IF;
            CONTINUE;
        END IF;
        chained_rows := chained_rows + 1;
        v_expect := evidence_hash(evidence_row_canonical(r));
        IF r.prev_hash IS DISTINCT FROM v_prev OR r.row_hash IS DISTINCT FROM v_expect THEN
            broken_rows := broken_rows + 1;
            IF first_break_id IS NULL THEN
                first_break_id := r.id;
            END IF;
        END IF;
        v_prev  := r.row_hash;
        head_id := r.id;
        head_hash := r.row_hash;
    END LOOP;

    -- All four guards, each on its exact table, present and enabled.
    guard_present := (
        SELECT count(*) = 4 FROM pg_trigger t
         WHERE NOT t.tgisinternal AND t.tgenabled <> 'D'
           AND (t.tgrelid::regclass::text, t.tgname) IN (
                ('compliance_results',        'trg_compliance_results_append_only'),
                ('compliance_results',        'trg_compliance_results_chain'),
                ('compliance_certifications', 'trg_compliance_certifications_append_only'),
                ('evidence_maintenance_log',  'trg_evidence_log_append_only')));
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION evidence_chain_verify() IS
  'Recomputes every compliance_results hash link in chain_seq order; unhashed rows count as broken. '
  'broken_rows > 0 or guard_present = false means the evidence store has been altered or unguarded; '
  'first_break_id is where. guard_present requires all four guard triggers on their exact tables.';
