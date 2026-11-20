-- layered_collection_read_map.sql — what layered collection reads before it runs.
--
-- The component map of step 1 as it stands now (detected, confirmed by an
-- operator, or unverified), with the kind and value of each matched signal, and
-- the service instance each host and component led to in earlier runs.
-- Read-only. Run by ansible/playbooks/collect_component_facts.yml.
-- The result is one base64 value: names stored in the database (unit, process
-- and container names came from hosts) never pass through a template.
SELECT translate(encode(convert_to(jsonb_build_object(
  'components', COALESCE((
      SELECT jsonb_agg(jsonb_build_object(
                 'hostname', c.hostname, 'host_id', c.host_id, 'component_key', c.component_key,
                 'status', c.status,
                 'evidence', (SELECT COALESCE(jsonb_agg(jsonb_build_object('kind', e->>'kind', 'value', e->>'value')), '[]'::jsonb)
                                FROM jsonb_array_elements(CASE WHEN jsonb_typeof(c.evidence) = 'array'
                                                               THEN c.evidence ELSE '[]'::jsonb END) e))
               ORDER BY c.hostname, c.component_key)
        FROM v_host_components_current c), '[]'::jsonb),
  'known_instances', COALESCE((
      SELECT jsonb_agg(jsonb_build_object('host', h, 'component_key', f.component_key, 'instance_id', f.instance_id))
        FROM v_component_facts_latest f, unnest(f.reached_through) h
       WHERE f.layer = 2 AND f.depth = 1 AND f.status = 'collected'), '[]'::jsonb)
)::text, 'UTF8'), 'base64'), E'\n', '') AS map_b64
