-- evidence_provenance.sql — make "which rule produced this verdict" answerable
--
-- Implements findings 1 and 2 of docs/AAC_EVIDENCE_QUALITY_ASSESSMENT.md.
-- Idempotent: safe to re-run.
--
-- THE PROBLEM
-- -----------
-- `policy_version` is free text doing four different jobs — "1.0" (1,600 rows),
-- "CIP-002 through CIP-015", a benchmark title, "mac-aap-demo-v1". None of it
-- identifies the policy that produced the verdict. Against a Rego library whose
-- submodule pointer moves most weeks, a verdict from March and one from August may
-- have come from materially different rules and nothing distinguishes them.
--
-- An auditor asks two questions that must both be answerable:
--   "show me the rule you applied"          -> policy_sha
--   "re-run it and show me the same result" -> project_sha + policy_sha together
--
-- Two SHAs, because they answer different halves:
--   project_sha — which compliance-repo commit ran (the playbook, the fact
--                 collection, the storage logic). AAP already knows this; it is
--                 the job's scm_revision.
--   policy_sha  — a digest of the policy set OPA actually had loaded
--                 when the verdict was rendered — NOT a git commit. A git SHA
--                 describes what was committed; only the loaded set describes
--                 what was evaluated, and the two diverge whenever a load fails
--                 or partially applies.
--
-- Both are nullable FOR NOW. Making them NOT NULL before every producer supplies
-- them would break 12 playbooks at once; `evidence_provenance_gaps` below names
-- who still needs updating, so the gap stays visible rather than forgotten.

ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS policy_sha  varchar(64);
ALTER TABLE compliance_results ADD COLUMN IF NOT EXISTS project_sha varchar(64);

COMMENT ON COLUMN compliance_results.policy_sha IS
  'Fingerprint of the policy set that rendered this verdict. NOT a git SHA: AAP '
  'exports the project without .git, and more importantly what decides a verdict is '
  'what OPA had LOADED, not what was committed (628 files shipped vs 310 loaded). '
  'Canonicalisation: OPA GET /v1/policies result, sorted by id, Ansible to_json, '
  'sha256. Reproducible only via the same canonicalisation - see the caveat in '
  'ansible/tasks/resolve_evidence_provenance.yml.';

COMMENT ON COLUMN compliance_results.project_sha IS
  'Compliance repo commit SHA that ran the assessment — the AAP job scm_revision. '
  'With policy_sha this makes a verdict reproducible.';

CREATE INDEX IF NOT EXISTS idx_results_policy_sha
    ON compliance_results (policy_sha) WHERE policy_sha IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Who is still writing evidence without provenance, or without a real subject.
-- Keeps the remaining work visible and attributable to a producer rather than
-- leaving it as an aggregate number nobody owns.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW evidence_provenance_gaps AS
SELECT policy_name,
       count(*)                                                  AS rows,
       count(*) FILTER (WHERE policy_sha  IS NULL)               AS missing_policy_sha,
       count(*) FILTER (WHERE project_sha IS NULL)               AS missing_project_sha,
       count(*) FILTER (WHERE hostname IS NULL OR hostname = ''
                           OR hostname = 'localhost')            AS missing_subject,
       max(evaluation_timestamp)                                 AS last_seen
  FROM compliance_results
 GROUP BY policy_name
HAVING count(*) FILTER (WHERE policy_sha IS NULL) > 0
    OR count(*) FILTER (WHERE hostname IS NULL OR hostname = '' OR hostname = 'localhost') > 0
 ORDER BY rows DESC;

-- ---------------------------------------------------------------------------
-- Provenance coverage — the metric to drive to 100%. Report on NEW rows only;
-- historical rows can never be given provenance retroactively and pretending
-- otherwise would be inventing evidence.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW evidence_provenance_coverage AS
SELECT date_trunc('day', evaluation_timestamp)::date        AS day,
       count(*)                                             AS results,
       count(*) FILTER (WHERE policy_sha IS NOT NULL)       AS with_policy_sha,
       count(*) FILTER (WHERE hostname IS NOT NULL
                          AND hostname <> ''
                          AND hostname <> 'localhost')      AS with_real_subject,
       round(100.0 * count(*) FILTER (WHERE policy_sha IS NOT NULL)
             / NULLIF(count(*), 0), 1)                      AS pct_provenanced
  FROM compliance_results
 GROUP BY 1 ORDER BY 1 DESC;
