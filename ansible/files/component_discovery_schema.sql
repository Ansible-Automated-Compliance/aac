-- component_discovery_schema.sql — which technology components run on which host.
--
-- Applied by ansible/playbooks/discover_host_components.yml. Additive and safe to
-- re-run: every statement is CREATE ... IF NOT EXISTS, CREATE OR REPLACE VIEW or
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS on a table this file owns. Nothing
-- here drops an object or touches a table of another feature, and nothing in
-- the product deletes rows from these tables.
--
-- Two maps, kept apart:
--   component_catalog    a copy of the shipped detection catalog (what CAN be found)
--   host_components      the per-host map, built only from discovery (what WAS found)
-- Operator overrides live in component_overrides and are applied by the views,
-- so the detection columns always show what detection found.
--
-- Reference: docs/reference/COMPONENT_DISCOVERY.md

CREATE TABLE IF NOT EXISTS component_discovery_runs (
    id                BIGSERIAL PRIMARY KEY,
    run_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    catalog_version   TEXT        NOT NULL,
    stale_after_days  INTEGER     NOT NULL DEFAULT 7,
    hosts_evaluated   INTEGER     NOT NULL DEFAULT 0,
    job_id            BIGINT,
    summary           JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS component_catalog (
    component_key      TEXT PRIMARY KEY,
    name               TEXT    NOT NULL,
    kind               TEXT    NOT NULL,
    collector          TEXT    NOT NULL DEFAULT 'none yet',
    loader_keys        TEXT[]  NOT NULL DEFAULT '{}',
    can_act            BOOLEAN NOT NULL DEFAULT false,
    can_map            BOOLEAN NOT NULL DEFAULT false,
    can_rank           BOOLEAN NOT NULL DEFAULT false,
    catalog_version    TEXT    NOT NULL,
    in_current_catalog BOOLEAN NOT NULL DEFAULT true,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS host_components (
    id                 BIGSERIAL PRIMARY KEY,
    host_id            VARCHAR(255) NOT NULL,
    hostname           VARCHAR(255),
    component_key      TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('detected', 'not_seen')),
    run_state          TEXT CHECK (run_state IN ('running', 'installed')),
    confidence         TEXT CHECK (confidence IN ('high', 'medium')),
    signal_kinds       TEXT[] NOT NULL DEFAULT '{}',
    evidence           JSONB  NOT NULL DEFAULT '[]'::jsonb,
    catalog_version    TEXT   NOT NULL,
    first_seen         TIMESTAMPTZ NOT NULL,
    last_seen          TIMESTAMPTZ NOT NULL,
    facts_id           BIGINT,
    facts_collected_at TIMESTAMPTZ,
    not_seen_since     TIMESTAMPTZ,
    not_seen_reason    TEXT CHECK (not_seen_reason IN
                         ('signal_gone_in_newer_facts', 'no_newer_facts', 'catalog_changed')),
    not_seen_detail    TEXT,
    last_run_id        BIGINT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (host_id, component_key)
);
CREATE INDEX IF NOT EXISTS idx_host_components_component ON host_components (component_key);
CREATE INDEX IF NOT EXISTS idx_host_components_status    ON host_components (status);

CREATE TABLE IF NOT EXISTS host_component_history (
    id            BIGSERIAL PRIMARY KEY,
    host_id       VARCHAR(255) NOT NULL,
    component_key TEXT NOT NULL,
    event         TEXT NOT NULL,
    from_status   TEXT,
    to_status     TEXT,
    detail        JSONB NOT NULL DEFAULT '{}'::jsonb,
    run_id        BIGINT,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_host_component_history_host
    ON host_component_history (host_id, component_key, recorded_at);

CREATE TABLE IF NOT EXISTS host_unrecognised (
    id                 BIGSERIAL PRIMARY KEY,
    host_id            VARCHAR(255) NOT NULL,
    hostname           VARCHAR(255),
    item_kind          TEXT NOT NULL CHECK (item_kind IN ('service', 'port')),
    item               TEXT NOT NULL,
    detail             JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             TEXT NOT NULL CHECK (status IN ('present', 'not_seen')),
    first_seen         TIMESTAMPTZ NOT NULL,
    last_seen          TIMESTAMPTZ NOT NULL,
    facts_id           BIGINT,
    facts_collected_at TIMESTAMPTZ,
    not_seen_since     TIMESTAMPTZ,
    not_seen_reason    TEXT CHECK (not_seen_reason IN
                         ('signal_gone_in_newer_facts', 'no_newer_facts', 'now_recognised')),
    last_run_id        BIGINT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (host_id, item_kind, item)
);

CREATE TABLE IF NOT EXISTS component_overrides (
    id            BIGSERIAL PRIMARY KEY,
    host          VARCHAR(255) NOT NULL,          -- host_id or hostname as stored in host_facts
    component_key TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('exclude', 'confirm', 'reclassify')),
    reclassify_to TEXT NOT NULL DEFAULT '',
    requested_by  TEXT NOT NULL CHECK (btrim(requested_by) <> ''),
    reason        TEXT NOT NULL CHECK (btrim(reason) <> ''),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    withdrawn_at  TIMESTAMPTZ,                    -- set when the entry leaves the operator's file
    UNIQUE (host, component_key, action, reclassify_to, requested_by, expires_at)
);
-- requested_by is what the entry declares. recorded_by is the account that
-- launched the job that recorded it, source is where the list came from
-- (file or variable), approved_by is the second person required to hide or
-- rename a privileged component.
ALTER TABLE component_overrides ADD COLUMN IF NOT EXISTS approved_by TEXT;
ALTER TABLE component_overrides ADD COLUMN IF NOT EXISTS recorded_by TEXT;
ALTER TABLE component_overrides ADD COLUMN IF NOT EXISTS source      TEXT NOT NULL DEFAULT 'file';

-- ── Views ────────────────────────────────────────────────────────────────────

-- Overrides with their state worked out at query time: an override past its
-- expiry stops applying without anything having to run.
CREATE OR REPLACE VIEW v_component_overrides AS
SELECT o.id, o.host, o.component_key, o.action, NULLIF(o.reclassify_to, '') AS reclassify_to,
       o.requested_by, o.reason, o.created_at, o.expires_at, o.withdrawn_at,
       CASE WHEN o.withdrawn_at IS NOT NULL THEN 'withdrawn'
            WHEN o.expires_at <= now()      THEN 'expired'
            ELSE 'in_force' END                                  AS state,
       (o.expires_at::date - now()::date)                        AS days_to_expiry,
       o.approved_by, o.recorded_by, o.source
  FROM component_overrides o;

-- The whole map: every stored row with the override in force (if any) beside
-- it, plus components an operator confirmed where detection found nothing.
-- `basis` says whether the effective answer comes from detection or an override.
CREATE OR REPLACE VIEW v_host_component_map AS
WITH run AS (
    SELECT COALESCE((SELECT stale_after_days FROM component_discovery_runs
                      ORDER BY id DESC LIMIT 1), 7) AS stale_after_days
), live AS (
    SELECT * FROM v_component_overrides WHERE state = 'in_force'
)
SELECT hc.host_id, hc.hostname,
       hc.component_key                                   AS detected_component,
       COALESCE(ov.reclassify_to, hc.component_key)       AS component_key,
       hc.status                                          AS detection_status,
       CASE WHEN ov.action = 'exclude' THEN 'excluded'
            WHEN ov.action = 'confirm' THEN 'confirmed'
            WHEN hc.status = 'not_seen' AND hc.not_seen_reason = 'no_newer_facts' THEN 'unverified'
            ELSE hc.status END                            AS effective_status,
       CASE WHEN ov.id IS NULL THEN 'detection' ELSE 'override' END AS basis,
       hc.run_state, hc.confidence, hc.signal_kinds, hc.evidence, hc.catalog_version,
       hc.first_seen, hc.last_seen, hc.facts_id, hc.facts_collected_at,
       hc.not_seen_since, hc.not_seen_reason, hc.not_seen_detail,
       CASE WHEN hc.status = 'detected'
                 AND hc.facts_collected_at < now() - make_interval(days => run.stale_after_days)
            THEN 'no newer facts since ' || to_char(hc.facts_collected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')
            WHEN hc.status = 'detected' THEN 'current'
            WHEN hc.not_seen_reason = 'no_newer_facts'
            THEN 'unverified: no newer facts since ' || to_char(hc.facts_collected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')
            ELSE 'not seen since ' || to_char(hc.not_seen_since AT TIME ZONE 'UTC', 'YYYY-MM-DD')
                 || ' (' || hc.not_seen_reason || ')' END  AS freshness,
       ov.action AS override_action, ov.requested_by AS override_by,
       ov.reason AS override_reason, ov.expires_at AS override_expires,
       ov.approved_by AS override_approved_by, ov.recorded_by AS override_recorded_by,
       ov.source AS override_source
  FROM host_components hc
  CROSS JOIN run
  LEFT JOIN LATERAL (
        SELECT * FROM live l
         WHERE l.component_key = hc.component_key AND l.host IN (hc.host_id, hc.hostname)
         ORDER BY l.created_at DESC, l.id DESC LIMIT 1) ov ON true
UNION ALL
SELECT l.host, l.host, l.component_key, l.component_key,
       'not_detected', 'confirmed', 'override',
       NULL, NULL, '{}'::text[], '[]'::jsonb, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       'confirmed by override; not detected',
       l.action, l.requested_by, l.reason, l.expires_at,
       l.approved_by, l.recorded_by, l.source
  FROM live l
 WHERE l.action = 'confirm'
   AND NOT EXISTS (SELECT 1 FROM host_components hc
                    WHERE hc.component_key = l.component_key AND l.host IN (hc.host_id, hc.hostname));

-- Auditor view 1: components currently on each host. A component whose host has
-- no newer usable facts stays listed (status `unverified`, or `detected` with a
-- "no newer facts since" freshness): a failed collection is not a removal.
CREATE OR REPLACE VIEW v_host_components_current AS
SELECT m.hostname, m.host_id, m.component_key, c.name AS component, c.kind,
       m.effective_status AS status, m.basis, m.run_state, m.confidence, m.freshness,
       m.first_seen, m.last_seen, m.facts_collected_at, m.catalog_version,
       m.override_action, m.override_by, m.override_reason, m.override_expires, m.evidence,
       m.override_approved_by, m.override_recorded_by, m.override_source
  FROM v_host_component_map m
  LEFT JOIN component_catalog c ON c.component_key = m.component_key
 WHERE m.effective_status IN ('confirmed', 'detected', 'unverified');

-- Auditor view 2: detected but not assessed. A component is listed when no
-- collector gathers its facts, when no policy bundle goes with it, or when no
-- stored result for any of its policy keys exists for that host.
CREATE OR REPLACE VIEW v_components_not_assessed AS
SELECT cur.hostname, cur.host_id, cur.component_key, cur.component, cur.kind,
       cur.confidence, cur.basis, c.collector, c.loader_keys, a.last_assessed_at,
       concat_ws('; ',
           CASE WHEN c.collector IS NULL OR c.collector = 'none yet' THEN 'no collector' END,
           CASE WHEN COALESCE(cardinality(c.loader_keys), 0) = 0 THEN 'no policy bundle' END,
           CASE WHEN cardinality(c.loader_keys) > 0 AND a.last_assessed_at IS NULL
                THEN 'no stored result for this host' END)  AS why_not_assessed
  FROM v_host_components_current cur
  LEFT JOIN component_catalog c ON c.component_key = cur.component_key
  LEFT JOIN LATERAL (
        SELECT max(r.evaluation_timestamp) AS last_assessed_at
          FROM compliance_results r
         WHERE r.framework = ANY (c.loader_keys)
           AND r.hostname IN (cur.hostname, cur.host_id)) a ON true
 WHERE c.collector IS NULL OR c.collector = 'none yet'
    OR COALESCE(cardinality(c.loader_keys), 0) = 0
    OR a.last_assessed_at IS NULL;

-- Auditor view 3: running, not recognised.
CREATE OR REPLACE VIEW v_host_unrecognised AS
SELECT u.hostname, u.host_id, u.item_kind, u.item, u.detail,
       u.first_seen, u.last_seen, u.facts_collected_at
  FROM host_unrecognised u
 WHERE u.status = 'present';

-- Auditor view 4: privileged services detected.
CREATE OR REPLACE VIEW v_privileged_services AS
SELECT cur.hostname, cur.host_id, cur.component_key, cur.component, cur.kind,
       c.can_act, c.can_map, c.can_rank,
       cur.status, cur.basis, cur.confidence, cur.run_state, cur.freshness, cur.last_seen
  FROM v_host_components_current cur
  JOIN component_catalog c ON c.component_key = cur.component_key
 WHERE c.can_act OR c.can_map OR c.can_rank;
