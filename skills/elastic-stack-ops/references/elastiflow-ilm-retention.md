# ElastiFlow ILM Retention — capping disk growth permanently

The durable fix for the recurring "disk fills → cluster RED" incident. Treats
the cause (unbounded data growth), not the symptom (full disk).

## How ElastiFlow ILM is structured

- A **single shared policy** named `elastiflow` governs ALL index types:
  `flow`, `telemetry_flow`, `metric`, `log`, `path`.
- Default phases:
  - `hot`: `rollover` every `1d` OR `20gb`/primary-shard, plus `forcemerge`
    (`max_num_segments: 2`, `best_compression`).
  - `delete`: `min_age: 7d` (the collector's shipped default) → too long for
    high-volume flow data.
- 5 composable index templates (`elastiflow-{flow,telemetry_flow,metric,log,path}-codex-2.5`)
  all reference `ilm.name = elastiflow`, so editing the one policy reaches all.

## The persistence guarantee (why this is safe)

Per ElastiFlow docs: **the collector creates a basic 7-day `elastiflow` policy
only if one does NOT already exist. It does not overwrite an existing policy.**
Therefore, once you PUT your edited policy, it survives every collector restart.
You do NOT need a compose env var (there is none for `delete.min_age`).

## Recipe — change retention to N days

ILM requires PUTting the WHOLE policy body (no partial patch). Read it, change
only `delete.min_age`, PUT it back, verify.

```bash
# 1. Read current policy (note the phases)
curl -s 'http://localhost:9200/_ilm/policy/elastiflow?pretty'

# 2. PUT the full policy with delete.min_age changed (example: 3d).
#    Strip runtime fields (version, modified_date, in_use_by) — keep only "policy".
curl -s -X PUT 'http://localhost:9200/_ilm/policy/elastiflow' \
  -H 'Content-Type: application/json' -d '{
  "policy": {
    "phases": {
      "hot": {
        "min_age": "0ms",
        "actions": {
          "rollover": { "max_age": "1d", "max_primary_shard_size": "20gb" },
          "forcemerge": { "max_num_segments": 2, "index_codec": "best_compression" }
        }
      },
      "delete": {
        "min_age": "3d",
        "actions": { "delete": { "delete_searchable_snapshot": true } }
      }
    }
  }
}'

# 3. Verify the change landed and the indices are managed by it
curl -s 'http://localhost:9200/_ilm/policy/elastiflow' | grep min_age
curl -s 'http://localhost:9200/elastiflow-flow-*/_ilm/explain?pretty' \
  | grep -E '"policy"|"phase"|"managed"'
# Expect: managed:true, policy:elastiflow, phase:hot (awaiting rollover)
```

`_ilm/_start` confirms ILM is RUNNING. `_ilm/retry` does NOT accept a wildcard
index and errors 400 if no index is in an error step — harmless, skip it unless
an index is actually stuck.

## Sizing intuition

Flow index grew ~1.9 GB in ~1h on the corp host → ~45 GB/day. So:
- 7d retention ≈ 315 GB (flow) + telemetry/metric → filled the 637 GB disk.
- 3d retention ≈ 135–150 GB total → comfortable headroom.

Pick `min_age` from `(disk_budget * 0.7) / daily_growth_GB`, then round down.

## Gotcha: live index count

`min_age` counts from the **rollover** of each index, not its creation. The
current day's index hasn't rolled yet, so you always see ~N+1 live indices per
type (N retained + 1 active). This is correct ILM behavior, not a leak.

## Versioning the policy

When committing the stack config to git, export the policy as a clean PUT body
(strip `version`/`modified_date`/`in_use_by`) so it's directly re-appliable with
`curl -d @ilm-policy-elastiflow.json`. On first deploy you MUST apply it after
`up` to override the collector's 7-day default.
