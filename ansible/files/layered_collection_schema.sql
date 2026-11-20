-- layered_collection_schema.sql — facts collected per technology component,
-- layer by layer, and what was found inside each component.
--
-- Applied by ansible/playbooks/collect_component_facts.yml. Additive and safe
-- to re-run: every statement is CREATE ... IF NOT EXISTS or CREATE OR REPLACE
-- VIEW on an object this file owns. Nothing here drops an object, alters a
-- table of another feature, or deletes a row. It reads two step-1 objects
-- (v_host_components_current, component_catalog) and changes neither.
--
-- Layers: 0 base host facts (host_facts) -> 1 detection (host_components) ->
-- 2 component, host side -> 3 component, service side -> 4 what is inside a
-- component (component_children), fed back to detection.
--
-- Reference: docs/reference/LAYERED_FACT_GATHERING.md

CREATE TABLE IF NOT EXISTS component_collection_runs (
    id               BIGSERIAL PRIMARY KEY,
    run_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    catalog_version  TEXT        NOT NULL,
    contract_version TEXT        NOT NULL,
    max_depth        INTEGER     NOT NULL,
    passes_run       INTEGER     NOT NULL DEFAULT 0,
    cost_filter      TEXT        NOT NULL,
    layer_filter     TEXT        NOT NULL,
    job_id           BIGINT,
    summary          JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- The collectors the shipped catalog declares, copied on each run so the
-- database can say which collector, cost and credential type goes with a row.
CREATE TABLE IF NOT EXISTS component_collectors (
    component_key      TEXT     NOT NULL,
    layer              SMALLINT NOT NULL CHECK (layer IN (2, 3)),
    collector          TEXT     NOT NULL,           -- tasks file name, or 'none yet'
    collector_version  TEXT,
    cost               TEXT     NOT NULL CHECK (cost IN ('cheap', 'heavy')),
    credential_type    TEXT,                        -- service side only
    access_needed      TEXT,                        -- least-privilege, read-only access the collector needs
    assess             BOOLEAN  NOT NULL DEFAULT true,
    contains           TEXT[]   NOT NULL DEFAULT '{}',
    catalog_version    TEXT     NOT NULL,
    in_current_catalog BOOLEAN  NOT NULL DEFAULT true,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (component_key, layer)
);

-- Component facts, keyed by service instance. An instance (a cluster, a
-- database server) is not a host: one instance can be reached through several
-- hosts (reached_through), and one host can carry several instances.
--
-- A row is added when the outcome for its key changes (status, reason, facts
-- or collector version). A run that finds the same outcome only moves
-- last_confirmed_at, so history is kept without one row per run.
-- status = 'not_collected' always carries the reason: no collector, no
-- credential, collector failed, host not reachable, size cap, depth limit.
CREATE TABLE IF NOT EXISTS component_facts (
    id                BIGSERIAL PRIMARY KEY,
    instance_id       TEXT     NOT NULL,
    component_key     TEXT     NOT NULL,
    layer             SMALLINT NOT NULL CHECK (layer IN (2, 3)),
    parent_kind       TEXT     NOT NULL CHECK (parent_kind IN ('host', 'instance')),
    parent_id         TEXT     NOT NULL,
    reached_through   TEXT[]   NOT NULL DEFAULT '{}',   -- inventory hosts the instance was reached through
    depth             INTEGER  NOT NULL DEFAULT 1 CHECK (depth >= 1),
    status            TEXT     NOT NULL CHECK (status IN ('collected', 'not_collected')),
    reason            TEXT     NOT NULL DEFAULT '',
    collector         TEXT,                             -- NULL when there is no collector
    collector_version TEXT,
    cost              TEXT CHECK (cost IN ('cheap', 'heavy')),
    credential_type   TEXT,
    catalog_version   TEXT     NOT NULL,
    collected_at      TIMESTAMPTZ NOT NULL,
    last_confirmed_at TIMESTAMPTZ NOT NULL,
    facts             JSONB    NOT NULL DEFAULT '{}'::jsonb,
    facts_bytes       INTEGER  NOT NULL DEFAULT 0,
    facts_sha256      TEXT     NOT NULL DEFAULT '',
    notes             JSONB    NOT NULL DEFAULT '[]'::jsonb,
    first_run_id      BIGINT,
    last_run_id       BIGINT,
    -- What the collector was pointed at: the identity the framework gives a
    -- target before the collector runs. It does not change when a collector
    -- returns a better instance identity, so the outcomes of one target line
    -- up from run to run.
    target_id         TEXT     NOT NULL,
    CHECK (status = 'collected' OR btrim(reason) <> '')
);
CREATE INDEX IF NOT EXISTS idx_component_facts_key
    ON component_facts (target_id, component_key, layer, parent_kind, parent_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_component_facts_component ON component_facts (component_key);
CREATE INDEX IF NOT EXISTS idx_component_facts_hosts ON component_facts USING gin (reached_through);

-- Inventory of what was found inside a component. Everything a collector
-- reports is listed with its parent, whether or not the catalog recognises it.
-- Collectors run only for recognised children whose catalog entry is flagged
-- for assessment (disposition 'assess'). Rows are never deleted: a child that
-- is no longer reported is marked not_seen.
CREATE TABLE IF NOT EXISTS component_children (
    id                   BIGSERIAL PRIMARY KEY,
    parent_instance_id   TEXT    NOT NULL,
    parent_component_key TEXT    NOT NULL,
    parent_layer         SMALLINT NOT NULL CHECK (parent_layer IN (2, 3)),
    via_host             TEXT    NOT NULL DEFAULT '',   -- host whose collector reported it ('' for the service side)
    child_kind           TEXT    NOT NULL,              -- signal kind, as in the detection catalog
    child_value          TEXT    NOT NULL,
    child_name           TEXT    NOT NULL DEFAULT '',
    detail               JSONB   NOT NULL DEFAULT '{}'::jsonb,
    recognised_as        TEXT,                          -- catalog key, NULL when not recognised
    child_instance_id    TEXT,
    disposition          TEXT    NOT NULL CHECK (disposition IN
                           ('assess', 'inventory_only', 'no_collector', 'depth_limit', 'not_recognised')),
    depth                INTEGER NOT NULL CHECK (depth >= 2),
    status               TEXT    NOT NULL DEFAULT 'present' CHECK (status IN ('present', 'not_seen')),
    first_seen           TIMESTAMPTZ NOT NULL,
    last_seen            TIMESTAMPTZ NOT NULL,
    not_seen_since       TIMESTAMPTZ,
    catalog_version      TEXT    NOT NULL,
    last_run_id          BIGINT,
    UNIQUE (parent_instance_id, parent_layer, via_host, child_kind, child_value, child_name)
);
CREATE INDEX IF NOT EXISTS idx_component_children_recognised ON component_children (recognised_as);

-- ── Views ────────────────────────────────────────────────────────────────────

-- The latest outcome for each target, component, layer and parent.
CREATE OR REPLACE VIEW v_component_facts_latest AS
SELECT DISTINCT ON (f.target_id, f.component_key, f.layer, f.parent_kind, f.parent_id) f.*
  FROM component_facts f
 ORDER BY f.target_id, f.component_key, f.layer, f.parent_kind, f.parent_id, f.id DESC;

-- Coverage. One row per detected component and layer:
--   facts collected              the collector ran and returned facts
--   detected, not assessed       with the reason (no collector, no credential,
--                                collector failed, host not reachable, ...)
-- A component on a host that no collection run has looked at yet is listed as
-- not assessed too. Components found inside another component (depth > 1) are
-- listed with their parent. "Running, not recognised" is v_host_unrecognised.
CREATE OR REPLACE VIEW v_component_coverage AS
SELECT cur.hostname, cur.component_key, cur.component, cur.kind,
       f.layer, f.instance_id, f.parent_kind, f.parent_id, COALESCE(f.depth, 1) AS depth,
       CASE WHEN f.status = 'collected' THEN 'facts collected'
            ELSE 'detected, not assessed' END                         AS coverage,
       COALESCE(NULLIF(f.reason, ''),
                CASE WHEN f.id IS NULL THEN 'no collection run has covered this component yet' END) AS reason,
       f.collector, f.collector_version, f.cost, f.credential_type,
       f.collected_at, f.last_confirmed_at, f.facts_bytes, f.catalog_version
  FROM v_host_components_current cur
  LEFT JOIN LATERAL (
        -- one outcome per layer for this host and component: the latest
        SELECT DISTINCT ON (x.layer) x.*
          FROM component_facts x
         WHERE x.component_key = cur.component_key AND x.depth = 1
           AND cur.hostname = ANY (x.reached_through)
         ORDER BY x.layer, x.id DESC) f ON true
UNION ALL
SELECT array_to_string(f.reached_through, ','), f.component_key, c.name, c.kind,
       f.layer, f.instance_id, f.parent_kind, f.parent_id, f.depth,
       CASE WHEN f.status = 'collected' THEN 'facts collected'
            ELSE 'detected, not assessed' END,
       NULLIF(f.reason, ''),
       f.collector, f.collector_version, f.cost, f.credential_type,
       f.collected_at, f.last_confirmed_at, f.facts_bytes, f.catalog_version
  FROM v_component_facts_latest f
  LEFT JOIN component_catalog c ON c.component_key = f.component_key
 WHERE f.depth > 1;

CREATE OR REPLACE VIEW v_component_coverage_collected AS
SELECT * FROM v_component_coverage WHERE coverage = 'facts collected';

CREATE OR REPLACE VIEW v_component_coverage_not_assessed AS
SELECT * FROM v_component_coverage WHERE coverage = 'detected, not assessed';

-- What is inside each component now, with the parent it was found through.
CREATE OR REPLACE VIEW v_component_children AS
SELECT ch.parent_instance_id, ch.parent_component_key, ch.parent_layer, ch.via_host,
       ch.child_kind, ch.child_value, ch.child_name, ch.recognised_as, ch.child_instance_id,
       ch.disposition, ch.depth, ch.first_seen, ch.last_seen, ch.detail
  FROM component_children ch
 WHERE ch.status = 'present';

-- Service instances and the hosts each one was reached through.
CREATE OR REPLACE VIEW v_component_instances AS
SELECT f.instance_id, f.component_key,
       array_agg(DISTINCT h ORDER BY h)                     AS reached_through,
       min(f.depth)                                         AS depth,
       max(f.collected_at) FILTER (WHERE f.status = 'collected') AS last_collected_at,
       array_agg(DISTINCT f.layer ORDER BY f.layer) FILTER (WHERE f.status = 'collected') AS layers_collected
  FROM v_component_facts_latest f
  LEFT JOIN LATERAL unnest(f.reached_through) h ON true
 GROUP BY f.instance_id, f.component_key;
