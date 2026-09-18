---
name: elastic-stack-ops
description: Operate Elasticsearch/Kibana/ElastiFlow Docker stacks safely.
version: 1.0.0
author: T-800 InfraOps (InfraOps)
license: MIT
metadata:
  hermes:
    tags: [elasticsearch, kibana, elastiflow, elk, docker, upgrade, cluster-health, netflow]
    category: devops
    requires_toolsets: [terminal]
---

# Elastic Stack Ops

Operate and upgrade Dockerized Elasticsearch / Kibana / ElastiFlow stacks for
Enterprise/Core. Covers the mandatory pre-upgrade safety gate, cluster-health
recovery, and disk-watermark incidents. Does NOT cover greenfield install or
multi-node cluster bootstrap.

## When to Use

- "Upgrade Elasticsearch / Kibana / ELK / ElastiFlow to latest"
- Cluster RED/YELLOW, unassigned shards, indices stuck read-only
- ElastiFlow stopped ingesting flows, disk full on an ES host
- Any change that restarts an Elasticsearch service

## Golden Rules (hard gates — do not skip)

1. **NEVER upgrade or restart a cluster that is not GREEN.** Restarting a RED
   cluster with unassigned *primary* shards risks making them permanently
   irrecoverable. Stabilize first, upgrade second.
2. **NEVER jump major versions blindly.** Check `index.version.created` on all
   indices — indices created by an older major can block a +2 major upgrade.
   Elastic requires stepping through majors (e.g. 7.x → 8.x → 9.x).
3. **Backup the compose + configs before touching anything.** Customizations
   for these stacks usually live entirely in the `docker-compose.yml` (env
   vars, tuning), not in named volumes.
4. **"Update Docker" is rarely the real need.** Check `docker --version` first;
   the engine is often already current. The risk is in the ES data/version, not
   the engine.

## Diagnose Before You Touch (read-only sweep)

Run this BEFORE proposing any change. ElastiFlow stacks commonly use **bind
mounts** (so `docker volume ls` is empty — the data is on the host filesystem).

```bash
# Engine + compose
docker --version; docker compose version
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'

# Where do data + compose live? (bind mounts hide here)
for c in elasticsearch kibana elastiflow-flow-collector; do
  docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' $c
  docker inspect -f 'configfile={{index .Config.Labels "com.docker.compose.project.config_files"}}' $c
done

# DISK FIRST — the #1 cause of RED clusters on these boxes
df -h /opt /var/lib/docker

# Cluster health + version
curl -s 'http://localhost:9200/_cluster/health?pretty'
curl -s 'http://localhost:9200' | grep number
curl -s 'http://localhost:9200/_cat/allocation?v&bytes=gb'
curl -s 'http://localhost:9200/_cluster/allocation/explain?pretty' -H 'Content-Type: application/json' -d '{}' | grep -E 'explanation|decision'

# Index-version compatibility gate (blocks major upgrades)
curl -s 'http://localhost:9200/_all/_settings/index.version.created?pretty' | grep -oE '"created" : "[0-9]+"' | sort | uniq -c
```

## Disk Watermark → RED Cluster (most common incident)

The causal chain, confirmed repeatedly on these hosts:
disk fills → ES crosses **flood-stage watermark (95%)** → ES sets indices
**read-only** automatically → ElastiFlow can't write → ingestion silently dies
for days/weeks → primary shards go unassigned → cluster **RED**.

The `allocation/explain` output names it directly ("above the high watermark...
actual used: 97%"). Full recovery recipe (free disk first, then clear blocks,
then drop replicas to 0 on single-node, then verify ingestion resumes) is in
`references/disk-watermark-recovery.md`.

Key remediation choices to put to the user (do not pick unilaterally — these
are production data decisions):
- **Expand disk** (preferred, no data loss): user adds a virtual disk →
  extend PV→VG→LV→ext4 online. Check `sudo vgs`/`pvs` for free extents first;
  if the LV already fills the partition, only a new disk helps.
- **Delete oldest rollover indices** (data loss): only if disk can't grow.
  Ask how much flow retention they actually need.

## ILM Retention — the DURABLE fix for the disk-fill class

Freeing/expanding disk only treats the symptom. The permanent fix is an **ILM
policy** that caps how long data lives. ElastiFlow indices are rollover-managed
by a single shared policy named `elastiflow`, with phases `hot` (rollover
1d/20gb + forcemerge) and `delete`. The default `delete.min_age` the collector
ships is **7d** — too long for these flow volumes (the flow index can grow
~45 GB/day, so 7d ≈ 300+ GB → the box fills). Lowering it (e.g. to `3d`) caps
the footprint.

Critical persistence detail (confirmed against ElastiFlow docs): **the collector
only CREATES the policy if it doesn't exist; it never overwrites an existing
one.** So once you edit the `elastiflow` policy, your retention survives every
collector restart — no compose change needed. There is NO env var for
`delete.min_age`; you edit the ES policy directly. Full recipe (read → edit only
`delete.min_age` → PUT whole policy body → verify with `_ilm/explain`) is in
`references/elastiflow-ilm-retention.md`. Note: `min_age` counts from the
*rollover* of each index, so you'll always see ~N+1 live indices per type.
Additional Kibana KQL and Lens visualization patterns are documented in `references/kibana-kql-and-lens.md`.

## Single-Node Replica Pitfall

`single-node` ES with `number_of_replicas: 1` can NEVER allocate replicas
(no second node) — they sit UNASSIGNED forever and inflate the unassigned
count, masking the real (primary) problem. On single-node, set replicas to 0
cluster-wide. A YELLOW caused only by phantom replicas is cosmetic; RED from
unassigned *primaries* is the real emergency.

## Security Note & Tenable/Nessus Remediation

These stacks frequently run `xpack.security.enabled=false` with `9200` bound to
`0.0.0.0`. Index names like random-string + `.htm`/`.txt`/`README` are a known
signature of automated ransom/wipe bots that scan exposed Elasticsearch. Flag
exposure to the user; don't assume it's benign.

- **Remediate Tenable/Nessus "Unrestricted Access" by binding to loopback:** Change
  `ports: - "9200:9200"` to `ports: - "127.0.0.1:9200:9200"` in `docker-compose.yml`.
  Because Kibana communicates over the internal Docker bridge network (`http://elasticsearch:9200`)
  and ElastiFlow collector uses `network_mode: host` pointing to `127.0.0.1:9200`,
  external binding is unnecessary. Loopback binding immediately closes
  unauthenticated external exposure without breaking local ingestion or requiring
  full X-Pack auth / certificate setup.

## Upgrade Procedure (only after GREEN + disk healthy)

1. Confirm cluster GREEN and disk < ~85%.
2. Take a snapshot (or at minimum cold-copy bind-mount dirs if no snapshot repo).
3. Check ElastiFlow's compatibility matrix for the target ES version — the
   collector pins which ES majors it supports.
4. Bump image tags in `docker-compose.yml` (prefer latest **same-major** first,
   e.g. 8.6 → latest 8.x; defer cross-major to a separate change).
5. `docker compose pull && docker compose up -d` — ES first (healthcheck
   gates Kibana via `depends_on: condition: service_healthy`).
6. **Restart ElastiFlow collector** after ES is healthy: the collector worker may
   back off after seeing connection refused during ES downtime and queue up flows
   (`UDP Server to Flow Decoder is 90% full`). Run `docker restart elastiflow-flow-collector`.
7. Verify: health GREEN, version bumped, Kibana up, and ElastiFlow doc count increasing
   (check `_count` on `elastiflow-flow-*` across 3-5 seconds to confirm non-zero delta).

## ElastiFlow Upgrade Gotchas (a blind tag bump WILL break the stack)

"Max version possible" for an ElastiFlow stack is bounded by the collector, NOT
by what Elastic ships. Confirmed against ElastiFlow docs (Jun 2026):

- **ElastiFlow supports only Elastic 7.x and 8.x — NOT 9.x.** 8.x has full
  support until Jan 15 2027. So "upgrade to latest" = **latest 8.x** (e.g.
  8.19.x), never 9.x, even though ES/Kibana 9.x images exist. Going to 9.x
  puts the stack in an unsupported combination.
- **The collector env-var schema was RENAMED across 7.x.** Old (≈7.13):
  `EF_FLOW_OUTPUT_ELASTICSEARCH_*`, `EF_FLOW_DECODER_*`. New (≈7.26):
  `EF_OUTPUT_ELASTICSEARCH_*`, `EF_PROCESSOR_DECODE_*`, `EF_PROCESSOR_ENRICH_*`.
  A blind collector tag bump silently breaks ingestion because the old vars are
  ignored. **Translate every customized env var** — full map in
  `references/elastiflow-envvar-migration.md`.
- **Collector v7.5+ requires persistence volumes** (`/etc/elastiflow` and
  `/var/lib/elastiflow/flowcoll`) — create them `chown 1000:1000` before `up`.
- **MaxMind enabled WITHOUT the `.mmdb` files = hard PANIC crashloop**, not a
  silent skip (`Maxmind ASN Enricher initialization failed: open
  .../GeoLite2-ASN.mmdb: no such file or directory`). If GeoLite2 DBs aren't
  mounted, set `EF_PROCESSOR_ENRICH_IPADDR_MAXMIND_{ASN,GEOIP}_ENABLE: "false"`
  to get the collector up, then offer to download the DBs as a follow-up. Full
  download/validate/enable/prove procedure (license-key vs GitHub mirror,
  `.mmdb` integrity check, path mapping, enrichment proof query) is in
  `references/elastiflow-maxmind-geolite2.md` + `scripts/validate_mmdb.py`.
- **Single-node replicas at the source:** make new rollover indices born GREEN
  with `EF_OUTPUT_ELASTICSEARCH_INDEX_TEMPLATE_REPLICAS: "0"` /
  `_SHARDS: "1"`. Editing ES templates by hand is futile — the collector
  recreates them on every start.
- **Verify version availability via the host, not Docker Hub.** Elastic images
  live on `docker.elastic.co` (Hub 404s; bare manifest API 401s). From the
  target host: `docker manifest inspect docker.elastic.co/elasticsearch/elasticsearch:<tag>`.
- **Validate plan-first:** `docker compose -f new.yml config` before `up`, and
  scp the edited compose from your workstation rather than fighting remote
  heredoc quoting over SSH (the `\n`/quotes get mangled).

## Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| `docker volume ls` empty but data exists | Bind mounts, not named volumes | `docker inspect` Mounts to find host paths |
| Cluster RED after "nothing changed" | Disk crossed flood-stage watermark | Free/expand disk, then clear read-only blocks |
| Indices won't accept writes | `index.blocks.read_only_allow_delete: true` auto-set | Clear block AFTER disk is healthy (see reference) |
| Replicas never allocate | single-node + replicas≥1 | Set `number_of_replicas: 0` cluster-wide |
| Tenable flags "Unrestricted Access" on 9200 | Port bound to `0.0.0.0:9200` with X-Pack disabled | Bind to `127.0.0.1:9200:9200` in compose |
| Collector queues full after ES restart | Worker connection backoff during downtime | `docker restart elastiflow-flow-collector` and verify `_count` delta |
| Upgrade fails on old indices | `index.version.created` from older major | Reindex or step through majors |

## Verification

- `curl -s localhost:9200/_cluster/health` → `"status":"green"`
- `df -h /opt` → comfortably below 85%
- ElastiFlow: newest index `creation.date` is recent (ingestion alive)
- `docker compose ps` → all services Up/healthy

## Versioning the Stack Config to Git

When asked to capture/back up the stack into git, version **config only, never
data**. Layout (one project dir, e.g. `elastiflow-stack/` in the infra repo):
`docker-compose.yml`, `elasticsearch/ilm-policy-elastiflow.json` (clean PUT
body), `elasticsearch/index-templates.json` (reference export), a `README.md`
(architecture, deploy-from-zero, customizations, retention, disk-full runbook),
and `scripts/download-maxmind.sh`. Rules:

- **`.gitignore` excludes** `esdata/`, `kibanadata/`, `flowcoll/lib/`, `*.mmdb`
  (binaries, 78 MB), `.env`, `*.key`/`*.license`, and `docker-compose.yml.bak`.
- **Scan for secrets before committing** (`grep -riE 'password|token|license_key|secret_token'`)
  — these stacks keep ES user/pass env vars empty, but confirm.
- **Export the ILM policy as a re-appliable PUT body** (strip `version`,
  `modified_date`, `in_use_by`).
- **Fix stale comments** carried from the original compose (e.g. the MaxMind
  "skips if absent" comment is wrong — it PANICs; see MaxMind gotcha).
- Deliver via **branch + PR** for a production repo unless told otherwise; set
  commit author to the user. Elastic images live on `docker.elastic.co`.
