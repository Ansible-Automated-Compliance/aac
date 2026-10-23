-- host_registry_schema.sql — the estate-continuity registry
--
-- One row per asset the estate has ever contained. It is how the
-- estate-continuity check remembers a host after the host has gone: the
-- inventory and the provider forget a deleted machine, so without this table a
-- disappearance leaves no trace to classify.
--
-- This is STATE, not evidence. It is updated in place by
-- ansible/playbooks/estate_continuity_check.yml. The evidence of each run's
-- classification is the append-only compliance_results row (framework
-- 'estate_continuity'), which is never edited.
--
-- Idempotent — all DDL uses IF NOT EXISTS. Apply once per compliance DB.

CREATE TABLE IF NOT EXISTS host_registry (
    hostname                   VARCHAR(255) PRIMARY KEY,
    first_seen_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_seen_in_inventory_at  TIMESTAMPTZ,
    inventory_name             VARCHAR(255),
    provider                   VARCHAR(50)  NOT NULL DEFAULT 'none',   -- aws_ec2 | none | ...
    provider_ref               VARCHAR(255),                           -- e.g. EC2 instance id
    provider_region            VARCHAR(50),
    lifecycle_state            VARCHAR(50)  NOT NULL DEFAULT 'new',    -- last state the policy returned
    state_since                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    retired_at                 TIMESTAMPTZ,
    retired_ref                VARCHAR(255),
    retired_by                 VARCHAR(255),
    updated_at                 TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_host_registry_state ON host_registry (lifecycle_state);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'compliance_reader') THEN
        GRANT SELECT ON host_registry TO compliance_reader;
    END IF;
END $$;
