-- component_discovery_read_hosts.sql — the stored facts that component detection reads.
--
-- One JSON document for all hosts in host_facts_latest, trimmed to the names
-- detection matches on: unit name, state and enablement; installed package
-- names; process names (the first 100 lines and the distinct command names);
-- listening sockets; running user-level units; running container images.
-- Package versions and every other fact domain stay in the database.
-- Read-only. Run by ansible/playbooks/discover_host_components.yml.
--
-- The result is ONE base64 value (`blob`). These names come from the managed
-- hosts, so they must not pass through Ansible as text it could template; only
-- scripts/component_discovery.py decodes the blob.
SELECT encode(convert_to(COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb)::text, 'UTF8'), 'base64') AS blob
  FROM (
SELECT hf.id AS facts_id, hf.host_id, hf.hostname,
       to_char(hf.collected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"') AS collected_at,
       jsonb_build_object(
         'services', jsonb_build_object(
             'all', (SELECT jsonb_object_agg(s.key, jsonb_build_object(
                                'state', s.value->>'state', 'status', s.value->>'status'))
                       FROM jsonb_each(CASE WHEN jsonb_typeof(hf.facts->'services'->'all') = 'object'
                                            THEN hf.facts->'services'->'all' ELSE '{}'::jsonb END) s),
             'enabled_at_boot', hf.facts->'services'->'enabled_at_boot',
             'user_units', hf.facts->'services'->'user_units'),
         'packages', jsonb_build_object(
             'installed', (SELECT jsonb_agg(k)
                             FROM jsonb_object_keys(CASE WHEN jsonb_typeof(hf.facts->'packages'->'installed') = 'object'
                                                         THEN hf.facts->'packages'->'installed' ELSE '{}'::jsonb END) k)),
         'processes', jsonb_build_object('processes_raw', hf.facts->'processes'->'processes_raw',
                                         'command_names', hf.facts->'processes'->'command_names'),
         'network', jsonb_build_object('listening_ports', hf.facts->'network'->'listening_ports'),
         'containers', hf.facts->'containers') AS facts
  FROM host_facts_latest hf
 ORDER BY hf.host_id
) t
