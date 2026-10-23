-- compliance_findings — the derived, stateful findings layer.
-- Owned by the aac_findings_sync role (applied idempotently each sync).
-- compliance_results stays the immutable evidence; this table is the
-- actionable index over it. Rows are never deleted: state transitions only.

CREATE TABLE IF NOT EXISTS compliance_findings (
    id             BIGSERIAL PRIMARY KEY,
    framework      VARCHAR(100) NOT NULL,
    control_id     VARCHAR(120) NOT NULL,
    subject        VARCHAR(255) NOT NULL,
    finding_type   VARCHAR(20)  NOT NULL DEFAULT 'violation',  -- violation | evidence_gap
    severity       VARCHAR(20),
    title          TEXT,
    refs           JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- cce/cci/nist_800_53/rule_id…
    status         VARCHAR(20)  NOT NULL DEFAULT 'open',       -- open | resolved | waived
    first_seen     TIMESTAMPTZ  NOT NULL,
    last_seen      TIMESTAMPTZ  NOT NULL,
    resolved_at    TIMESTAMPTZ,
    times_seen     INTEGER      NOT NULL DEFAULT 1,
    last_result_id BIGINT,                                     -- newest observing compliance_results.id
    UNIQUE (framework, control_id, subject, finding_type)
);

CREATE INDEX IF NOT EXISTS idx_findings_control ON compliance_findings (control_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_findings_subject ON compliance_findings (subject)    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_findings_refs    ON compliance_findings USING gin (refs);

-- Blast radius: one control → every system currently failing it.
-- "SELECT * FROM findings_blast_radius WHERE control_id = 'CIS 1.1.1'"
CREATE OR REPLACE VIEW findings_blast_radius AS
SELECT framework,
       control_id,
       finding_type,
       COUNT(*)                          AS affected_count,
       array_agg(subject ORDER BY subject) AS affected_subjects,
       MIN(first_seen)                   AS oldest_first_seen
FROM compliance_findings
WHERE status = 'open'
GROUP BY framework, control_id, finding_type;

-- Target list: one system → everything open on it, oldest first.
-- "SELECT * FROM findings_system_targets WHERE subject = 'host01'"
CREATE OR REPLACE VIEW findings_system_targets AS
SELECT subject, framework, control_id, finding_type, severity, title,
       first_seen, last_seen, times_seen
FROM compliance_findings
WHERE status = 'open'
ORDER BY subject, first_seen;

-- Reference blast radius: find every system carrying a given CCE/CCI/rule id
-- (the security-hole question when the hole is known by reference, not by
-- framework control number).
-- "SELECT * FROM findings_ref_radius WHERE ref_value = 'CCE-90638-3'"
CREATE OR REPLACE VIEW findings_ref_radius AS
SELECT ref.value AS ref_value,
       f.framework, f.control_id, f.subject, f.status, f.first_seen
FROM compliance_findings f,
     LATERAL (
        SELECT jsonb_array_elements_text(
                 CASE jsonb_typeof(v.val) WHEN 'array' THEN v.val
                      ELSE jsonb_build_array(v.val) END) AS value
        FROM jsonb_each(f.refs) AS v(key, val)
     ) AS ref
WHERE f.status = 'open';
