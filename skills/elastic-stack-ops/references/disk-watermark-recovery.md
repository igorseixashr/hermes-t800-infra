# Disk Watermark → RED Cluster Recovery Recipe

Recovery procedure for an Elasticsearch node that filled its disk, crossed the
flood-stage watermark, set indices read-only, and went RED. Order matters:
**free disk FIRST**, then clear blocks, then fix allocation. Clearing blocks
while still over the watermark just re-triggers them.

## 0. Confirm the diagnosis

```bash
curl -s 'http://localhost:9200/_cluster/allocation/explain?pretty' \
  -H 'Content-Type: application/json' -d '{}' | grep -E 'explanation|decision'
# Look for: "above the high watermark ... actual used: [9x%]"

# Severity check — are PRIMARIES unassigned (true emergency) or only replicas (cosmetic)?
curl -s 'http://localhost:9200/_cat/shards?h=prirep,state' | sort | uniq -c
#   p STARTED  / p UNASSIGNED  <- UNASSIGNED primaries = real data risk
#   r UNASSIGNED                <- replicas only (single-node) = phantom, harmless
```

Default ES watermarks: low=85%, high=90%, flood-stage=95% (this box showed
high=95%). Once flood-stage trips, ES adds `index.blocks.read_only_allow_delete`
to every index automatically.

## 1. Free disk space (pick the user-approved path)

**Path A — expand disk (no data loss, preferred):**
```bash
# Check for free extents in the VG first
sudo vgs ; sudo pvs ; lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
# If LV already fills the partition (common), the VM needs a NEW virtual disk
# added at the hypervisor (vCenter). Then, online, no downtime:
sudo pvcreate /dev/sdX
sudo vgextend ubuntu-vg /dev/sdX
sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv
sudo resize2fs /dev/ubuntu-vg/ubuntu-lv   # ext4; use xfs_growfs for xfs
```

**Path B — delete oldest rollover indices (DATA LOSS, only if disk can't grow):**
```bash
# List oldest first, delete from the top until disk < ~85%
curl -s 'http://localhost:9200/_cat/indices?h=index,creation.date.string,store.size&s=creation.date&bytes=gb'
curl -s -XDELETE 'http://localhost:9200/elastiflow-flow-codex-2.5-rollover-000001'
# Repeat oldest-first. Confirm retention need with the user BEFORE deleting.
```

## 2. Clear the read-only block (ONLY after disk is healthy)

```bash
# Verify disk is actually below watermark now
df -h /opt

# Clear the auto-set block cluster-wide
curl -s -XPUT 'http://localhost:9200/_all/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index.blocks.read_only_allow_delete": null}'
```

## 3. Single-node: drop replicas to 0

On a `discovery.type=single-node` cluster, replicas can never allocate. Setting
them to 0 clears the phantom UNASSIGNED replica shards and lets the cluster
reach GREEN.

```bash
curl -s -XPUT 'http://localhost:9200/_all/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index":{"number_of_replicas":0}}'

# Also set it on the index template / ILM so new rollover indices inherit 0.
```

## 4. Re-trigger allocation of unassigned primaries

```bash
curl -s -XPOST 'http://localhost:9200/_cluster/reroute?retry_failed=true'
```

## 5. Verify recovery

```bash
curl -s 'http://localhost:9200/_cluster/health?pretty'   # want "green"
curl -s 'http://localhost:9200/_cat/shards?h=prirep,state' | sort | uniq -c
df -h /opt

# Confirm ingestion resumed — newest index creation.date should be recent
curl -s 'http://localhost:9200/_cat/indices?h=index,creation.date.string&s=creation.date' | tail -3
# If ElastiFlow still isn't writing, restart it last:
docker compose restart elastiflow-flow-collector
```

## Notes from the field

- Engine was Docker 29.6.0 / Compose 2.40.3 on Ubuntu 24.04 — already current;
  the user's "update Docker" request was a red herring vs. the real disk/RED issue.
- Stack: ES + Kibana 8.6.0 + `elastiflow/flow-collector:7.13.0`, single-node,
  security disabled, 9200 on 0.0.0.0. All 147 indices created on 8.6 (no major
  upgrade block). Data ~577G in `/opt/elastiflow/esdata` bind mount.
- Watch for a `<random>.htm` index appearing — possible ransom-bot artifact on
  the exposed (security-off) endpoint; investigate rather than assume benign.
