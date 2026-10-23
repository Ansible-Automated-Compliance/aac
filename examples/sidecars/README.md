# Sidecar Datasets (ADR-001)

Sidecar datasets provide organizational context that cannot be discovered
from endpoint `gather_facts` alone.

## Available Sidecars

| File | Type | Frameworks | Collection Method |
|------|------|-----------|-------------------|
| `digital_sovereignty.yml` | `digital_sovereignty` | Digital Sovereignty (7 domains) | Manual + cloud APIs |
| `nerc_cip.yml` | `nerc_cip` | NERC-CIP (CIP-002 to CIP-015) | Manual + CMDB |

## Time Alignment

**All sidecars run on the same nightly schedule as core `gather_facts`.**

This ensures that when a compliance assessment joins core facts with sidecar
data, both datasets are from the same collection window. The
`sidecar_datasets_latest` view always returns the most recent sidecar per
type+entity, which will match the most recent `host_facts` snapshot.

Two schedules at 02:00 UTC daily (both created by `seed_facts_collection_template.yml`):
- `AAC Nightly Fact Collection` → `aac_gather_facts.yml` (all systems)
- `AAC Nightly Sidecar Collection` → `aac_store_sidecar.yml` (digital_sovereignty default)

Additional sidecar types (nerc_cip, etc.) can be triggered manually or by adding
more schedules/workflow nodes for each `entity_id` + `sidecar_type` combination.

## Storing a Sidecar

```bash
# Via AAP (preferred):
# Launch "AAC - Store Sidecar Dataset" with:
#   sidecar_type: digital_sovereignty
#   entity_id:    EuroBank AG
#   sidecar_file: examples/sidecars/digital_sovereignty.yml
```

## Querying Sidecars

```sql
-- Most recent sidecar for an entity
SELECT sidecar_type, entity_id, collected_at, data
FROM sidecar_datasets_latest
WHERE sidecar_type = 'digital_sovereignty'
  AND entity_id = 'EuroBank AG';

-- All sidecar history for trending
SELECT collected_at, data->>'review_date' as review_date
FROM sidecar_datasets
WHERE sidecar_type = 'digital_sovereignty'
ORDER BY collected_at DESC;
```

## Adding a New Sidecar Type

1. Create `examples/sidecars/<type>.yml` with your schema
2. Add the type to the AAP survey choices in `seed_facts_collection_template.yml`
3. The `aac_store_sidecar.yml` playbook stores any valid YAML — no code changes needed
