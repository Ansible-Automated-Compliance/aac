-- patch_closure_schema.sql — proof that an exposure actually closed
--
-- Stage 12 of the patch lifecycle. The distinction this implements:
--
--   "we deployed the patch"   is a report of an ACTION
--   "the finding no longer matches"  is proof of an OUTCOME
--
-- A vulnerability platform can produce the first. An auditor asks for the
-- second. Without this loop the platform's belief about the estate silently
-- drifts from reality, and the next CVE match is computed against stale
-- inventory.
--
-- The method is deliberately simple and therefore defensible: re-measure the
-- host, compare what is installed NOW against what was installed when the
-- finding was raised and against the version that fixes it. No trust is placed
-- in the remediation job's own success report.

CREATE TABLE IF NOT EXISTS patch_closure_evidence (
    id                 BIGSERIAL PRIMARY KEY,
    verified_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- What was claimed to be at risk.
    cve_id             VARCHAR(32)  NOT NULL,
    severity           VARCHAR(16),
    kev_member         BOOLEAN      NOT NULL DEFAULT false,
    hostname           VARCHAR(255) NOT NULL,
    vendor             VARCHAR(255) NOT NULL,
    product            VARCHAR(255) NOT NULL,

    -- The three versions that decide the outcome.
    version_at_finding VARCHAR(100),   -- what patch_worklist recorded
    version_now        VARCHAR(100),   -- what the host reports today
    fixed_version      VARCHAR(100),   -- what upstream says resolves it

    outcome            VARCHAR(20)  NOT NULL,
    evidence_note      TEXT,

    UNIQUE (cve_id, hostname, vendor, product, verified_at)
);

COMMENT ON COLUMN patch_closure_evidence.outcome IS
  'closed_exact   — installed version now equals the fixed version. Strongest proof. '
  'closed_removed — the product is no longer installed on this host at all. '
  'changed_review — version moved but does not equal the fixed version. NOT counted '
  '                 as closed: it may be a newer fixed build or an unrelated change, '
  '                 and a version-string comparison cannot tell them apart. '
  'still_exposed  — version is unchanged. The remediation did not take effect. '
  'host_absent    — host no longer reports inventory. Cannot be proven either way.';

CREATE INDEX IF NOT EXISTS idx_closure_outcome  ON patch_closure_evidence (outcome);
CREATE INDEX IF NOT EXISTS idx_closure_cve      ON patch_closure_evidence (cve_id);
CREATE INDEX IF NOT EXISTS idx_closure_host     ON patch_closure_evidence (hostname);
CREATE INDEX IF NOT EXISTS idx_closure_verified ON patch_closure_evidence (verified_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_reader') THEN
        GRANT SELECT ON patch_closure_evidence TO compliance_reader;
    END IF;
END
$$;
