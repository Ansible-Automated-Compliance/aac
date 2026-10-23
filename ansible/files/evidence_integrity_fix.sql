-- evidence_integrity_fix.sql — make compliance_results attributable and fail-closed
--
-- Implements findings 3 and 4 of docs/AAC_EVIDENCE_QUALITY_ASSESSMENT.md.
-- Idempotent: safe to re-run. Every statement is guarded.
--
-- WHAT THIS FIXES
-- ---------------
-- 1. `framework` was documented NOT NULL in CLAUDE.md but is actually nullable, so
--    906 rows (33% of the corpus) landed with no framework at all. The failure that
--    was supposed to be loud and immediate has been silent since January.
-- 2. Nothing rejects an empty result at the storage boundary, so a framework that
--    returns `{}` — `iec_62443` has done exactly this since June — appends rows
--    claiming zero controls. **An assessment that found nothing and an assessment
--    that never ran currently produce identical rows.**
--
-- WHAT IT DELIBERATELY DOES NOT DO
-- --------------------------------
-- It does not delete or rewrite any verdict. Backfill only fills in what was
-- missing, and every touched row records the correction in `metadata._integrity_fix`
-- so the correction is itself auditable. Correcting evidence without recording that
-- you corrected it is the same class of defect this file exists to remove.

-- ---------------------------------------------------------------------------
-- MAINTENANCE PATH. compliance_results is append-only (evidence_append_only.sql):
-- the UPDATEs below are only allowed because this session declares maintenance,
-- and every row they touch is recorded in evidence_maintenance_log with its full
-- previous content. The hash chain breaks at each touched row on purpose —
-- evidence_chain_verify() will name them; that is the point, not a defect.
-- ---------------------------------------------------------------------------
SET aac.evidence_maintenance = 'on';
SET aac.evidence_maintenance_note = 'evidence_integrity_fix.sql: backfill/normalise framework attribution (AAC_EVIDENCE_QUALITY_ASSESSMENT findings 3-4)';

-- ---------------------------------------------------------------------------
-- 0. Backup before schema change (CLAUDE.md rule 7). Skipped if already taken today.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    bk text := 'compliance_results_bk_' || to_char(now(), 'YYYYMMDD');
BEGIN
    IF to_regclass('public.' || bk) IS NULL THEN
        EXECUTE format('CREATE TABLE %I AS SELECT * FROM compliance_results', bk);
        RAISE NOTICE 'backup created: %', bk;
    ELSE
        RAISE NOTICE 'backup already exists today: %', bk;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 1. Attribution map — policy_name -> canonical framework key
--
-- Every mapping below was derived from the producers actually present in the
-- corpus, not invented. `CIS RHEL 9 (Fedora)` maps to cis_rhel9 because the RHEL 9
-- benchmark is what was applied; `CIS Fedora 39` gets its own key because it is a
-- different benchmark.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE fw_map(policy_name text PRIMARY KEY, framework text) ON COMMIT DROP;
INSERT INTO fw_map VALUES
  ('AMI NIST IR 7628 Rev 1',                          'ami'),
  ('AMI Head-End Security',                           'ami'),
  ('AMI Device Compliance',                           'ami'),
  ('NIST IR 7628',                                    'ami'),
  ('CIS Fedora 39',                                   'cis_fedora39'),
  ('CIS RHEL 9 (Fedora)',                             'cis_rhel9'),
  ('CIS RHEL 9',                                      'cis_rhel9'),
  ('CIS Amazon Linux 2023',                           'cis_amazon_linux_2023'),
  ('CIS Ubuntu 22.04',                                'cis_ubuntu_2204'),
  ('CIS VyOS Router',                                 'cis_vyos'),
  ('CIS pfSense Firewall',                            'cis_pfsense'),
  ('CIS Windows Server 2022',                         'cis_windows_2022'),
  ('Digital Sovereignty',                             'digital_sovereignty'),
  ('NERC CIP',                                        'nerc_cip'),
  ('NERC CIP-015 INSM',                               'nerc_cip'),
  ('ncsc_caf_4',                                      'ncsc_caf_4'),
  ('sentinel-ansible/sentinel_ansible_compliant.yml', 'sentinel_ansible'),
  ('sentinel-ansible/sentinel_ansible_example.yml',   'sentinel_ansible');

-- ---------------------------------------------------------------------------
-- 2. Backfill NULL framework, recording the correction in metadata
-- ---------------------------------------------------------------------------
UPDATE compliance_results c
   SET framework = m.framework,
       metadata  = COALESCE(c.metadata, '{}'::jsonb) || jsonb_build_object(
                     '_integrity_fix', jsonb_build_object(
                       'at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                       'action', 'backfilled framework from policy_name',
                       'derived_from', c.policy_name,
                       'by', 'evidence_integrity_fix.sql'))
  FROM fw_map m
 WHERE c.framework IS NULL
   AND c.policy_name = m.policy_name;

-- ---------------------------------------------------------------------------
-- 3. Normalise legacy display-name framework values to canonical keys.
--
-- 'AMI Device Compliance', 'AMI Head-End Security' and 'NIST IR 7628' were stored
-- as framework VALUES alongside 'ami'. Left alone, a query for AMI evidence silently
-- misses them — the same defect as a NULL, just harder to spot. The original value
-- is preserved in metadata.
-- ---------------------------------------------------------------------------
UPDATE compliance_results c
   SET framework = m.framework,
       metadata  = COALESCE(c.metadata, '{}'::jsonb) || jsonb_build_object(
                     '_integrity_fix', jsonb_build_object(
                       'at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                       'action', 'normalised legacy framework label to canonical key',
                       'previous_framework', c.framework,
                       'by', 'evidence_integrity_fix.sql'))
  FROM fw_map m
 WHERE c.framework = m.policy_name
   AND c.framework <> m.framework;

-- ---------------------------------------------------------------------------
-- 4. Anything still unattributed becomes an explicit 'unclassified' rather than
--    NULL. NULL says "we don't know we don't know"; 'unclassified' is a claim we
--    can search for and clear later.
-- ---------------------------------------------------------------------------
UPDATE compliance_results
   SET framework = 'unclassified',
       metadata  = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                     '_integrity_fix', jsonb_build_object(
                       'at', to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SSOF'),
                       'action', 'no mapping for policy_name; marked unclassified',
                       'derived_from', policy_name,
                       'by', 'evidence_integrity_fix.sql'))
 WHERE framework IS NULL;

-- ---------------------------------------------------------------------------
-- 5. Make the documented constraint real
-- ---------------------------------------------------------------------------
ALTER TABLE compliance_results ALTER COLUMN framework SET NOT NULL;

-- ---------------------------------------------------------------------------
-- 6. Fail-closed gate: a stored result must claim at least one control.
--
-- Added NOT VALID on purpose. Existing violating rows are GRANDFATHERED and left
-- visible rather than deleted — they are the evidence that this gap existed. The
-- constraint applies to every new row from now on.
--
-- Find the grandfathered rows with:
--   SELECT * FROM compliance_results WHERE total_controls IS NULL OR total_controls = 0;
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'compliance_results_nonempty') THEN
        ALTER TABLE compliance_results
          ADD CONSTRAINT compliance_results_nonempty
          CHECK (total_controls IS NOT NULL AND total_controls > 0) NOT VALID;
        RAISE NOTICE 'fail-closed gate added (NOT VALID: existing rows grandfathered)';
    ELSE
        RAISE NOTICE 'fail-closed gate already present';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 7. A view naming what is still wrong, so it stays visible instead of forgotten
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW evidence_integrity_exceptions AS
SELECT id, hostname, framework, policy_name, total_controls, evaluation_timestamp,
       CASE
         WHEN total_controls IS NULL OR total_controls = 0 THEN 'empty result stored before the gate existed'
         WHEN framework = 'unclassified'                   THEN 'no framework mapping for this producer'
         WHEN hostname IS NULL OR hostname = ''            THEN 'no subject'
         WHEN hostname = 'localhost'                       THEN 'subject is the execution context, not an asset'
       END AS exception
  FROM compliance_results
 WHERE total_controls IS NULL OR total_controls = 0
    OR framework = 'unclassified'
    OR hostname IS NULL OR hostname = '' OR hostname = 'localhost';
