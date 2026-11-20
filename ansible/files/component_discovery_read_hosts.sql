-- component_discovery_read_hosts.sql — the stored facts that component detection reads.
--
-- One row per host from host_facts_latest, trimmed to the names detection
-- matches on: unit name, state and enablement; installed package names;
-- process names; listening sockets; running container images when a collector
-- stores them. Package versions and every other fact domain stay in the
-- database. Read-only. Run by ansible/playbooks/discover_host_components.yml.
SELECT hf.id AS facts_id, hf.host_id, hf.hostname,
       to_char(hf.collected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"') AS collected_at,
       jsonb_build_object(
         'services', jsonb_build_object(
             'all', (SELECT jsonb_object_agg(s.key, jsonb_build_object(
                                'state', s.value->>'state', 'status', s.value->>'status'))
                       FROM jsonb_each(CASE WHEN jsonb_typeof(hf.facts->'services'->'all') = 'object'
                                            THEN hf.facts->'services'->'all' ELSE '{}'::jsonb END) s),
             'enabled_at_boot', hf.facts->'services'->'enabled_at_boot'),
         'packages', jsonb_build_object(
             'installed', (SELECT jsonb_agg(k)
                             FROM jsonb_object_keys(CASE WHEN jsonb_typeof(hf.facts->'packages'->'installed') = 'object'
                                                         THEN hf.facts->'packages'->'installed' ELSE '{}'::jsonb END) k)),
         'processes', jsonb_build_object('processes_raw', hf.facts->'processes'->'processes_raw'),
         'network', jsonb_build_object('listening_ports', hf.facts->'network'->'listening_ports'),
         'containers', hf.facts->'containers') AS facts
  FROM host_facts_latest hf
 ORDER BY hf.host_id
