-- control_state_schema.sql — per-control results: passes as well as fails.
--
-- compliance_results holds one summary row per assessment run and
-- compliance_findings one row per failing control. An auditor also asks which
-- controls PASSED, and since when. This file adds:
--
--   control_state           one row per (hostname, framework, control_id): the
--                           control's current status and when it last changed.
--                           A row is updated in place; it is NOT a row per run
--                           (350 controls x 1,000 hosts x daily would be
--                           350,000 rows a day for almost no new information).
--   control_state_history   append-only: one row each time a control's status
--                           changes for a host, including its first sighting.
--   control_state_current   view: the state rows with the age of each status.
--   control_state_summary   view: counts per status per host and framework.
--   control_state_record()  the ONLY write path. SECURITY DEFINER, so the
--                           least-privilege evidence writer (INSERT + SELECT
--                           only) can record a run without holding UPDATE on
--                           anything.
--
-- Statuses come from the policy library's compliance_report.control_results:
--   pass | fail | evidence_missing | not_attested | not_applicable
-- plus two set here:
--   not_reported   the control was in an earlier run for this host and
--                  framework and is absent from the latest one (the benchmark
--                  version, the profile or the module changed). It never
--                  silently stays "pass".
--   invalid        the report carried a status that is not a plain lower-case
--                  word.
--
-- Idempotent: safe to re-run on a new or an existing database. Reference:
-- docs/reference/PER_CONTROL_RESULTS.md.

CREATE TABLE IF NOT EXISTS control_state (
    hostname        VARCHAR(255) NOT NULL,
    framework       VARCHAR(100) NOT NULL,
    control_id      VARCHAR(100) NOT NULL,
    status          VARCHAR(40)  NOT NULL,
    basis           VARCHAR(40),
    profile         TEXT,
    in_scope        BOOLEAN      NOT NULL DEFAULT TRUE,
    since           TIMESTAMPTZ  NOT NULL,
    last_seen       TIMESTAMPTZ  NOT NULL,
    last_result_id  BIGINT       NOT NULL,
    PRIMARY KEY (hostname, framework, control_id)
);

CREATE INDEX IF NOT EXISTS idx_control_state_framework_status
    ON control_state (framework, status);

CREATE TABLE IF NOT EXISTS control_state_history (
    id           BIGSERIAL    PRIMARY KEY,
    hostname     VARCHAR(255) NOT NULL,
    framework    VARCHAR(100) NOT NULL,
    control_id   VARCHAR(100) NOT NULL,
    from_status  VARCHAR(40),
    to_status    VARCHAR(40)  NOT NULL,
    changed_at   TIMESTAMPTZ  NOT NULL,
    result_id    BIGINT       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_control_state_history_subject
    ON control_state_history (hostname, framework, control_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_control_state_history_changed
    ON control_state_history (changed_at);

-- ── History is append-only ───────────────────────────────────────────────────
-- Same convention as the evidence tables: a rewrite needs a stated reason in
-- aac.evidence_maintenance_note for the session (retention pruning, a repair).
CREATE OR REPLACE FUNCTION control_state_history_append_only() RETURNS trigger AS $$
BEGIN
    IF COALESCE(current_setting('aac.evidence_maintenance_note', true), '') = '' THEN
        RAISE EXCEPTION 'control_state_history is append-only: % refused. Maintenance requires a reason: SET aac.evidence_maintenance_note = ''<why, by whom, ticket>''', TG_OP;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_control_state_history_append_only ON control_state_history;
CREATE TRIGGER trg_control_state_history_append_only
    BEFORE UPDATE OR DELETE ON control_state_history
    FOR EACH ROW EXECUTE FUNCTION control_state_history_append_only();

DROP TRIGGER IF EXISTS trg_control_state_history_no_truncate ON control_state_history;
CREATE TRIGGER trg_control_state_history_no_truncate
    BEFORE TRUNCATE ON control_state_history
    FOR EACH STATEMENT EXECUTE FUNCTION control_state_history_append_only();

-- ── The write path ───────────────────────────────────────────────────────────
-- One call per stored result. p_controls is the report's control_results list:
-- [{"id": "1.1.1.1", "status": "pass", "basis": "evidence", "in_scope": true,
--   "profile": [...]}, ...]. An empty or absent list writes nothing.
--
-- The result row must exist and belong to the same framework: state can only
-- be recorded against a stored result. A run older than the state it would
-- overwrite (a replayed or out-of-order result) is refused for that control.
CREATE OR REPLACE FUNCTION control_state_record(
    p_result_id bigint,
    p_hostname  text,
    p_framework text,
    p_controls  jsonb
) RETURNS TABLE (controls_reported integer, status_changes integer, controls_not_reported integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    v_now        timestamptz := clock_timestamp();
    v_reported   integer := 0;
    v_changes    integer := 0;
    v_missing    integer := 0;
BEGIN
    IF p_controls IS NULL OR jsonb_typeof(p_controls) <> 'array' OR jsonb_array_length(p_controls) = 0 THEN
        RETURN QUERY SELECT 0, 0, 0;
        RETURN;
    END IF;
    IF COALESCE(btrim(p_hostname), '') = '' OR COALESCE(btrim(p_framework), '') = '' THEN
        RAISE EXCEPTION 'control_state_record: hostname and framework are required';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM compliance_results r WHERE r.id = p_result_id AND r.framework = p_framework) THEN
        RAISE EXCEPTION 'control_state_record: result % is not a stored % result', p_result_id, p_framework;
    END IF;

    WITH incoming AS (
        SELECT DISTINCT ON (btrim(c.id))
               btrim(c.id)                                              AS control_id,
               CASE WHEN c.status ~ '^[a-z_]{1,40}$' THEN c.status ELSE 'invalid' END AS status,
               left(c.basis, 40)                                        AS basis,
               CASE jsonb_typeof(c.profile)
                    WHEN 'array'  THEN (SELECT string_agg(p, '; ') FROM jsonb_array_elements_text(c.profile) AS p)
                    WHEN 'string' THEN c.profile #>> '{}'
                    ELSE NULL END                                       AS profile,
               COALESCE(c.in_scope, TRUE)                               AS in_scope,
               TRUE                                                     AS reported
        FROM jsonb_to_recordset(p_controls)
             AS c(id text, status text, basis text, in_scope boolean, profile jsonb)
        WHERE COALESCE(btrim(c.id), '') <> '' AND length(btrim(c.id)) <= 100
        ORDER BY btrim(c.id)
    ),
    gone AS (
        SELECT s.control_id, 'not_reported'::text AS status, s.basis, s.profile, s.in_scope, FALSE AS reported
        FROM control_state s
        WHERE s.hostname = p_hostname AND s.framework = p_framework
          AND s.status <> 'not_reported'
          AND s.last_result_id < p_result_id
          AND NOT EXISTS (SELECT 1 FROM incoming i WHERE i.control_id = s.control_id)
    ),
    wanted AS (
        SELECT * FROM incoming
        UNION ALL
        SELECT * FROM gone
    ),
    current AS (
        SELECT w.*, s.status AS old_status, s.last_result_id AS old_result_id
        FROM wanted w
        LEFT JOIN control_state s
               ON s.hostname = p_hostname AND s.framework = p_framework AND s.control_id = w.control_id
    ),
    usable AS (
        SELECT * FROM current WHERE old_result_id IS NULL OR old_result_id <= p_result_id
    ),
    hist AS (
        INSERT INTO control_state_history (hostname, framework, control_id, from_status, to_status, changed_at, result_id)
        SELECT p_hostname, p_framework, u.control_id, u.old_status, u.status, v_now, p_result_id
        FROM usable u
        WHERE u.old_status IS DISTINCT FROM u.status
        RETURNING 1
    ),
    up AS (
        INSERT INTO control_state AS s
               (hostname, framework, control_id, status, basis, profile, in_scope, since, last_seen, last_result_id)
        SELECT p_hostname, p_framework, u.control_id, u.status, u.basis, u.profile, u.in_scope, v_now, v_now, p_result_id
        FROM usable u
        ON CONFLICT (hostname, framework, control_id) DO UPDATE SET
            since          = CASE WHEN s.status IS DISTINCT FROM EXCLUDED.status THEN EXCLUDED.since ELSE s.since END,
            status         = EXCLUDED.status,
            basis          = EXCLUDED.basis,
            profile        = EXCLUDED.profile,
            in_scope       = EXCLUDED.in_scope,
            -- a control that went missing keeps the time and result of its last report
            last_seen      = CASE WHEN EXCLUDED.status = 'not_reported' THEN s.last_seen      ELSE EXCLUDED.last_seen      END,
            last_result_id = CASE WHEN EXCLUDED.status = 'not_reported' THEN s.last_result_id ELSE EXCLUDED.last_result_id END
        RETURNING 1
    )
    SELECT (SELECT count(*) FROM usable WHERE reported),
           (SELECT count(*) FROM hist),
           (SELECT count(*) FROM usable WHERE NOT reported)
      INTO v_reported, v_changes, v_missing;

    RETURN QUERY SELECT v_reported, v_changes, v_missing;
END;
$$;

REVOKE ALL ON FUNCTION control_state_record(bigint, text, text, jsonb) FROM PUBLIC;

-- ── Views ────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW control_state_current AS
SELECT s.hostname,
       s.framework,
       s.control_id,
       s.status,
       s.basis,
       s.profile,
       s.in_scope,
       s.since,
       s.last_seen,
       s.last_result_id,
       r.policy_version,
       r.evaluation_timestamp AS last_result_at
FROM control_state s
LEFT JOIN compliance_results r ON r.id = s.last_result_id;

CREATE OR REPLACE VIEW control_state_summary AS
SELECT hostname,
       framework,
       count(*) FILTER (WHERE in_scope AND status <> 'not_reported')            AS controls,
       count(*) FILTER (WHERE in_scope AND status = 'pass')                     AS pass,
       count(*) FILTER (WHERE in_scope AND status = 'fail')                     AS fail,
       count(*) FILTER (WHERE in_scope AND status = 'evidence_missing')         AS evidence_missing,
       count(*) FILTER (WHERE in_scope AND status = 'not_attested')             AS not_attested,
       count(*) FILTER (WHERE in_scope AND status = 'not_applicable')           AS not_applicable,
       count(*) FILTER (WHERE status = 'not_reported')                          AS not_reported,
       count(*) FILTER (WHERE in_scope AND status NOT IN
             ('pass','fail','evidence_missing','not_attested','not_applicable','not_reported')) AS other,
       count(*) FILTER (WHERE NOT in_scope AND status <> 'not_reported')        AS out_of_scope,
       max(last_seen)                                                           AS last_seen
FROM control_state
GROUP BY hostname, framework;

-- ── Grants ───────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_reader') THEN
        GRANT SELECT ON control_state, control_state_history, control_state_current, control_state_summary
            TO compliance_reader;
    END IF;
    -- The evidence writer records state through the function only.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_writer') THEN
        GRANT SELECT ON control_state, control_state_history, control_state_current, control_state_summary
            TO compliance_writer;
        GRANT EXECUTE ON FUNCTION control_state_record(bigint, text, text, jsonb) TO compliance_writer;
    END IF;
END
$$;
